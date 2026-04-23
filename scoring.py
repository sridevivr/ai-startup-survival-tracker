"""
Survival scoring for the AI Startup Survival Tracker.

Given a list of Signals objects (from tracker.py), compute:
    * a 0-100 survival_score
    * a coarse status label
    * a signal_coverage indicator (how many signals we actually resolved)

The score is a weighted combination of seven components. Each component
returns a value in [0, 1]. Weights are intentionally conservative — the
goal is to surface outliers (clearly dead, clearly thriving) without
over-penalising quiet-but-alive companies.

If you are reading the output as a VC: treat the score as a *triage* tool,
not a judgment. A low score is a reason to investigate, not a verdict.
"""
from __future__ import annotations

import json
import os
from typing import Optional


# --------------------------------------------------------------------------
# Weights
# --------------------------------------------------------------------------
# Tuned so that a "healthy but quiet" company (live site, fresh wayback,
# no github, no blog, no careers page) still scores ~55 rather than 0.
#
# News was added as a seventh component. News is the only signal that
# reflects the outside world's view of the company (everyone else is
# self-reported by the startup's own surface area), so it carries real
# weight — 0.15, on par with blog/github/freshness.

WEIGHTS = {
    "website":   0.20,  # is the site even up?
    "freshness": 0.10,  # has the homepage / wayback changed recently?
    "blog":      0.10,  # are they still publishing?
    "github":    0.15,  # are they still shipping code?
    "hiring":    0.20,  # are they still hiring?
    "news":      0.15,  # what does the press say? (Google News RSS)
    "override":  0.10,  # manual-notes-based adjustment
}

STATUS_THRESHOLDS = [
    (80, "Thriving"),
    (65, "Healthy"),
    (45, "Watchlist"),
    (25, "Dormant"),
    (0,  "Likely Dead"),
]

# Keywords in the 'notes' field that deterministically set status
PIVOT_MARKERS = ("pivot", "acquihire", "acquired", "licensing deal", "acquisition", "rebranded")
DEAD_MARKERS = ("shut down", "ceased", "defunct", "bankrupt", "liquidated")


# --------------------------------------------------------------------------
# Component scores
# --------------------------------------------------------------------------


def _website_score(sig) -> Optional[float]:
    if sig.http_status is None:
        return None
    if 200 <= sig.http_status < 300:
        return 1.0
    if 300 <= sig.http_status < 400:
        return 0.85
    if sig.http_status in (401, 403):
        return 0.5  # site exists but gated
    if 400 <= sig.http_status < 500:
        return 0.2
    return 0.0  # 5xx


def _freshness_score(sig) -> Optional[float]:
    days = sig.wayback_last_snapshot_days
    if days is None:
        return None
    if days <= 14:   return 1.0
    if days <= 30:   return 0.85
    if days <= 90:   return 0.6
    if days <= 180:  return 0.35
    if days <= 365:  return 0.15
    return 0.0


def _blog_score(sig) -> Optional[float]:
    days = sig.feed_last_post_days
    if days is None:
        return None
    if days <= 30:   return 1.0
    if days <= 90:   return 0.75
    if days <= 180:  return 0.45
    if days <= 365:  return 0.2
    return 0.0


def _github_score(sig) -> Optional[float]:
    commits = sig.github_commits_90d
    if commits is None:
        return None
    if commits >= 100: return 1.0
    if commits >= 30:  return 0.8
    if commits >= 5:   return 0.5
    if commits >= 1:   return 0.25
    return 0.0


def _hiring_score(sig) -> Optional[float]:
    if sig.careers_page_found is None:
        return None
    if not sig.careers_page_found:
        return 0.15  # no careers page is a mild negative, not a death signal
    jobs = sig.jobs_detected or 0
    if jobs >= 20: return 1.0
    if jobs >= 5:  return 0.8
    if jobs >= 1:  return 0.55
    return 0.35  # page exists but no jobs found — ambiguous


def _override_score(sig) -> Optional[float]:
    joined = " | ".join(sig.notes).lower() if sig.notes else ""
    if not joined:
        return None
    if any(m in joined for m in DEAD_MARKERS):
        return 0.0
    if any(m in joined for m in PIVOT_MARKERS):
        return 0.4   # not dead, but the original entity is gone
    return None


def _news_score(sig) -> Optional[float]:
    """News signal component.

    Returns None if we have no news data for this company — keeps coverage
    honest rather than baking an assumption into the score.

    The rubric, in priority order:
      * death_signal (shutdown/bankruptcy/layoffs in recent headline) → 0.0
      * health_signal (funding/IPO/launches in recent headline)       → 1.0
      * recent coverage with no explicit signal                       → scaled
        by recency of last mention (fresh press presence is mildly positive)
      * no recent coverage at all                                     → 0.2
    """
    death = getattr(sig, "news_death_signal", None)
    health = getattr(sig, "news_health_signal", None)
    last_days = getattr(sig, "news_last_mention_days", None)
    count = getattr(sig, "news_item_count_180d", None)

    # If every news field is None we have no data — abstain.
    if death is None and health is None and last_days is None and count is None:
        return None

    if death:
        return 0.0
    if health:
        return 1.0
    if last_days is None or count == 0:
        # We checked the news and found nothing in the last 180 days.
        # That's a weak negative (silent press ≠ dead, but not healthy).
        return 0.2
    if last_days <= 30:   return 0.7
    if last_days <= 90:   return 0.55
    if last_days <= 180:  return 0.4
    return 0.25


# --------------------------------------------------------------------------
# Combine
# --------------------------------------------------------------------------


def _weighted(components: dict[str, Optional[float]]) -> tuple[float, float]:
    """Return (score_0_to_100, coverage_0_to_1)."""
    total_w = 0.0
    weighted_sum = 0.0
    resolved = 0
    for key, val in components.items():
        w = WEIGHTS[key]
        if val is not None:
            weighted_sum += val * w
            total_w += w
            resolved += 1
    if total_w == 0:
        return 0.0, 0.0
    score = (weighted_sum / total_w) * 100
    coverage = resolved / len(components)
    return round(score, 1), round(coverage, 2)


def _label_for(sig, score: float, coverage: float) -> str:
    joined = " | ".join(sig.notes).lower() if sig.notes else ""
    # Notes-based overrides always win — they're human-curated ground truth.
    if any(m in joined for m in DEAD_MARKERS):
        return "Likely Dead"
    if any(m in joined for m in PIVOT_MARKERS):
        return "Pivoted / Absorbed"
    # News death signal is near-ground-truth ONLY when it comes from a
    # trusted publication. An accessipos.com "Hey Pi IPO" clickbait piece
    # is not grounds for labeling a company dead. Untrusted death hits
    # still lower the numeric score via _news_score, but don't flip the
    # label — that's reserved for evidence we can actually defend.
    if (getattr(sig, "news_death_signal", False)
            and getattr(sig, "news_death_source_trusted", False)):
        return "Likely Dead"
    # If we have no observed signals at all, don't pretend to judge. This
    # matters for seeded rows (e.g. fresh Product Hunt entries) where the
    # tracker hasn't yet run — otherwise every unenriched row would be
    # labeled "Likely Dead" by default, which is the opposite of true.
    if coverage == 0.0:
        return "Not Yet Enriched"
    for threshold, label in STATUS_THRESHOLDS:
        if score >= threshold:
            return label
    return "Unknown"


def score_one(sig) -> None:
    components = {
        "website":   _website_score(sig),
        "freshness": _freshness_score(sig),
        "blog":      _blog_score(sig),
        "github":    _github_score(sig),
        "hiring":    _hiring_score(sig),
        "news":      _news_score(sig),
        "override":  _override_score(sig),
    }
    score, coverage = _weighted(components)
    sig.survival_score = score
    sig.signal_coverage = coverage
    sig.status = _label_for(sig, score, coverage)


def merge_news_into(signals: list, news_path: str = "output/news.json") -> int:
    """Fold news.json into signal objects (name → fields).

    Returns number of signals updated. Safe to call even if news.json
    doesn't exist — it's a no-op.
    """
    if not os.path.exists(news_path):
        return 0
    try:
        with open(news_path, encoding="utf-8") as f:
            news = json.load(f)
    except (OSError, json.JSONDecodeError):
        return 0
    updated = 0
    for s in signals:
        rec = news.get(s.name)
        if not isinstance(rec, dict) or "error" in rec:
            continue
        for k in (
            "news_item_count_180d", "news_item_count_raw",
            "news_last_mention_days",
            "news_death_signal", "news_health_signal",
            "news_death_headline", "news_death_link",
            "news_death_source", "news_death_source_domain",
            "news_death_source_trusted",
            "news_health_headline", "news_health_link",
            "news_health_source", "news_health_source_domain",
            "news_health_source_trusted",
        ):
            if k in rec and hasattr(s, k):
                setattr(s, k, rec[k])
        updated += 1
    return updated


def score_all(signals: list, news_path: str = "output/news.json") -> None:
    merge_news_into(signals, news_path)
    for s in signals:
        score_one(s)
