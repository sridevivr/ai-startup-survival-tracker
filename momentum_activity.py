"""Step 2 (visible half) — compute per-company momentum activity score,
write back to data/master.csv as a new column.

Reuses the component scorers from scoring.py (which already return 0–1
floats with sensible thresholds). Combines them with a two-layer model:

    Layer 1 — alive baseline
        website 2xx and no death-signal news → 0.30
        otherwise → 0.00 (death-locked)

    Layer 2 — activity boost (over the 0.30 baseline)
        boost = mean of (news, freshness, hiring, blog, github) component
        scores, skipping None. Missing signals abstain — they don't
        penalize the way the survival score does.

    Final: round((baseline + (1 - baseline) * boost) * 100)

Why two layers: 70% of the broader cohort has no above-baseline signal,
so a pure sum collapses to 0 for most companies. The baseline keeps
quiet-but-alive companies readable. A buzzing company tops out near 100.
"""
from __future__ import annotations

import csv
import json
import os
from collections import Counter

from scoring import (
    _website_score, _news_score, _freshness_score,
    _blog_score, _github_score, _hiring_score,
)

ROOT = os.path.dirname(os.path.abspath(__file__))
MASTER_CSV = os.path.join(ROOT, "data", "master.csv")
SIGNALS_JSON = os.path.join(ROOT, "output", "signals.json")

# Master schema: Step 1 had 9 cols. Step 2 adds activity_score before notes.
MASTER_COLUMNS = [
    "name", "website", "founded_year",
    "sector", "sub-sector", "functionality",
    "funding", "signals", "activity_score", "notes",
]


class _SigProxy:
    """Make a dict from signals.json look like the dataclass scoring.py
    expects — missing attrs return None instead of AttributeError."""
    __slots__ = ("_d",)
    def __init__(self, d: dict) -> None:
        self._d = d
    def __getattr__(self, name):
        return self._d.get(name)


def activity_score(sig_dict: dict) -> float:
    """Two-layer momentum score, 0–100."""
    sig = _SigProxy(sig_dict)
    ws = _website_score(sig)
    death = bool(sig_dict.get("news_death_signal"))
    death_trusted = bool(sig_dict.get("news_death_source_trusted"))
    # Real death signal (trusted) locks us to 0.0.
    if death and death_trusted:
        return 0.0
    alive = ws is not None and ws >= 0.5
    if not alive:
        return 0.0
    baseline = 0.30

    boost_components: list[float] = []
    for fn in (_news_score, _freshness_score, _hiring_score, _blog_score, _github_score):
        v = fn(sig)
        if v is not None:
            boost_components.append(v)
    boost = sum(boost_components) / len(boost_components) if boost_components else 0.0

    final = baseline + (1.0 - baseline) * boost
    return round(min(1.0, final) * 100, 1)


def load_signals() -> dict[str, dict]:
    with open(SIGNALS_JSON, encoding="utf-8") as f:
        return {r["name"]: r for r in json.load(f)}


def main() -> None:
    sigs = load_signals()
    with open(MASTER_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    distribution: Counter[str] = Counter()
    for r in rows:
        sig = sigs.get(r["name"], {})
        score = activity_score(sig)
        r["activity_score"] = score
        # bucket for histogram
        if score == 0:
            distribution["0 (locked dead)"] += 1
        elif score < 35:
            distribution["1–34 (alive, quiet)"] += 1
        elif score < 55:
            distribution["35–54 (light activity)"] += 1
        elif score < 75:
            distribution["55–74 (active)"] += 1
        else:
            distribution["75–100 (buzzing)"] += 1

    # Write back with the new column
    with open(MASTER_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MASTER_COLUMNS)
        w.writeheader()
        for r in rows:
            # Make sure all columns exist (notes may be missing on some rows)
            out = {k: r.get(k, "") for k in MASTER_COLUMNS}
            w.writerow(out)

    print(f"Computed activity_score for {len(rows)} companies in {MASTER_CSV}")
    print()
    print("Distribution:")
    for bucket in ["0 (locked dead)", "1–34 (alive, quiet)", "35–54 (light activity)",
                   "55–74 (active)", "75–100 (buzzing)"]:
        if bucket in distribution:
            print(f"  {distribution[bucket]:>3}  {bucket}")
    print()

    # Top 5 / bottom 5 sanity check
    scored = [(r["name"], r["activity_score"], r["sector"], r["functionality"]) for r in rows]
    scored.sort(key=lambda x: -x[1])
    print("Top 5 by activity score:")
    for name, score, s, f in scored[:5]:
        print(f"  {score:>5}  {name[:32]:<32}  {s} × {f}")
    print()
    print("Bottom 5 by activity score:")
    for name, score, s, f in scored[-5:]:
        print(f"  {score:>5}  {name[:32]:<32}  {s} × {f}")


if __name__ == "__main__":
    main()
