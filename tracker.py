"""
AI Startup Survival Tracker
===========================

Collects public health signals for AI startups and computes a "survival score".

Run:
    python tracker.py --input data/startups.csv --output output/results.json

Signals collected (all from public sources, no auth required):
    * Website uptime + HTTP status
    * Homepage last-modified / content hash
    * Blog / RSS feed freshness (days since last post)
    * GitHub organization commit activity (90-day window)
    * Careers page presence + detected job postings
    * Wayback Machine last snapshot date (freshness proxy)

All collectors are best-effort. Any signal that fails to resolve is recorded as
``None`` and down-weighted in the scoring step rather than crashing the run.

This file is intentionally dependency-light: only ``requests`` is required.
``feedparser`` and ``beautifulsoup4`` are used opportunistically if available.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import requests

try:
    from bs4 import BeautifulSoup  # type: ignore
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    import feedparser  # type: ignore
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False


USER_AGENT = (
    "Mozilla/5.0 (compatible; AIStartupSurvivalTracker/0.1; "
    "+https://github.com/example/ai-startup-survival-tracker)"
)
DEFAULT_TIMEOUT = 10
COMMON_FEED_PATHS = ["/feed", "/rss", "/rss.xml", "/blog/feed", "/blog/rss", "/feed.xml", "/atom.xml"]
COMMON_CAREER_PATHS = ["/careers", "/jobs", "/company/careers", "/about/careers", "/join"]


# --------------------------------------------------------------------------
# Signal container
# --------------------------------------------------------------------------


@dataclass
class Signals:
    name: str
    website: str
    category: str = ""
    founded: str = ""
    # raw signals
    http_status: Optional[int] = None
    ssl_ok: Optional[bool] = None
    homepage_bytes: Optional[int] = None
    homepage_title: Optional[str] = None
    feed_last_post_days: Optional[int] = None
    github_commits_90d: Optional[int] = None
    github_last_commit_days: Optional[int] = None
    careers_page_found: Optional[bool] = None
    jobs_detected: Optional[int] = None
    wayback_last_snapshot_days: Optional[int] = None
    # news signals (from tracker_news.py / output/news.json)
    news_item_count_180d: Optional[int] = None
    news_item_count_raw: Optional[int] = None
    news_last_mention_days: Optional[int] = None
    news_death_signal: Optional[bool] = None
    news_health_signal: Optional[bool] = None
    news_death_headline: str = ""
    news_death_link: str = ""
    news_death_source: str = ""
    news_death_source_domain: str = ""
    news_death_source_trusted: Optional[bool] = None
    news_health_headline: str = ""
    news_health_link: str = ""
    news_health_source: str = ""
    news_health_source_domain: str = ""
    news_health_source_trusted: Optional[bool] = None
    # score + label, filled in by scorer
    survival_score: Optional[float] = None
    status: Optional[str] = None
    signal_coverage: Optional[float] = None
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    checked_at: str = ""


# --------------------------------------------------------------------------
# Collectors
# --------------------------------------------------------------------------


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})
    return s


def check_website(sig: Signals, sess: requests.Session) -> Optional[str]:
    """Fetch homepage, record status, title, size. Returns HTML body or None."""
    try:
        r = sess.get(sig.website, timeout=DEFAULT_TIMEOUT, allow_redirects=True)
        sig.http_status = r.status_code
        sig.ssl_ok = sig.website.startswith("https://") and r.ok
        sig.homepage_bytes = len(r.content)
        if r.ok and r.text:
            m = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.I | re.S)
            if m:
                sig.homepage_title = re.sub(r"\s+", " ", m.group(1)).strip()[:200]
            return r.text
    except requests.exceptions.SSLError as e:
        sig.ssl_ok = False
        sig.errors.append(f"ssl:{type(e).__name__}")
    except Exception as e:  # noqa: BLE001
        sig.errors.append(f"http:{type(e).__name__}")
    return None


def check_feed(sig: Signals, sess: requests.Session, html: Optional[str]) -> None:
    """Find an RSS/Atom feed and compute days since last post."""
    candidates: list[str] = []
    if html and HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
        for link in soup.find_all("link", rel="alternate"):
            t = (link.get("type") or "").lower()
            href = link.get("href")
            if href and ("rss" in t or "atom" in t or "xml" in t):
                candidates.append(urljoin(sig.website, href))
    for path in COMMON_FEED_PATHS:
        candidates.append(urljoin(sig.website, path))

    seen: set[str] = set()
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        try:
            r = sess.get(url, timeout=DEFAULT_TIMEOUT)
            if not r.ok or "xml" not in r.headers.get("Content-Type", "").lower() and "<rss" not in r.text[:500] and "<feed" not in r.text[:500]:
                continue
            latest = _latest_feed_date(r.text)
            if latest:
                sig.feed_last_post_days = (datetime.now(timezone.utc) - latest).days
                return
        except Exception as e:  # noqa: BLE001
            sig.errors.append(f"feed:{type(e).__name__}")


def _latest_feed_date(xml_text: str) -> Optional[datetime]:
    if HAS_FEEDPARSER:
        try:
            f = feedparser.parse(xml_text)
            dates = []
            for e in f.entries[:30]:
                for key in ("published_parsed", "updated_parsed"):
                    t = getattr(e, key, None)
                    if t:
                        dates.append(datetime(*t[:6], tzinfo=timezone.utc))
            if dates:
                return max(dates)
        except Exception:
            pass
    # Regex fallback
    dates: list[datetime] = []
    for m in re.finditer(r"<(?:pubDate|updated|published)>([^<]+)</", xml_text):
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                d = datetime.strptime(m.group(1).strip(), fmt)
                if d.tzinfo is None:
                    d = d.replace(tzinfo=timezone.utc)
                dates.append(d)
                break
            except ValueError:
                continue
    return max(dates) if dates else None


def check_github(sig: Signals, sess: requests.Session, org: str) -> None:
    """Sum commits across an org's repos in the last 90 days using public API."""
    if not org:
        return
    try:
        r = sess.get(
            f"https://api.github.com/orgs/{org}/repos?per_page=100&sort=pushed",
            timeout=DEFAULT_TIMEOUT,
        )
        if r.status_code == 404:
            # Maybe it's a user, not an org
            r = sess.get(
                f"https://api.github.com/users/{org}/repos?per_page=100&sort=pushed",
                timeout=DEFAULT_TIMEOUT,
            )
        if not r.ok:
            sig.errors.append(f"gh:{r.status_code}")
            return
        repos = r.json()
        now = datetime.now(timezone.utc)
        total_commits = 0
        latest_push: Optional[datetime] = None
        for repo in repos[:20]:  # cap to avoid rate limits
            pushed = repo.get("pushed_at")
            if pushed:
                d = datetime.fromisoformat(pushed.replace("Z", "+00:00"))
                latest_push = max(latest_push or d, d)
            name = repo.get("name")
            if not name:
                continue
            cr = sess.get(
                f"https://api.github.com/repos/{org}/{name}/commits?per_page=100",
                timeout=DEFAULT_TIMEOUT,
            )
            if cr.ok:
                for c in cr.json():
                    iso = c.get("commit", {}).get("author", {}).get("date")
                    if iso:
                        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                        if (now - d).days <= 90:
                            total_commits += 1
        sig.github_commits_90d = total_commits
        if latest_push:
            sig.github_last_commit_days = (now - latest_push).days
    except Exception as e:  # noqa: BLE001
        sig.errors.append(f"gh:{type(e).__name__}")


def check_careers(sig: Signals, sess: requests.Session) -> None:
    """Look for a careers page and count job-like links."""
    for path in COMMON_CAREER_PATHS:
        url = urljoin(sig.website, path)
        try:
            r = sess.get(url, timeout=DEFAULT_TIMEOUT, allow_redirects=True)
            if not r.ok:
                continue
            sig.careers_page_found = True
            text = r.text.lower()
            # Heuristic: count anchors that look like job listings
            job_links = re.findall(r'href="[^"]*(?:/jobs/|/careers/|/positions/|greenhouse\.io|lever\.co|ashbyhq\.com|workable\.com)[^"]*"', text)
            sig.jobs_detected = len(set(job_links))
            return
        except Exception:
            continue
    sig.careers_page_found = False


def check_wayback(sig: Signals, sess: requests.Session) -> None:
    """Use the Wayback Machine availability API to find most recent snapshot."""
    try:
        r = sess.get(
            "https://archive.org/wayback/available",
            params={"url": sig.website},
            timeout=DEFAULT_TIMEOUT,
        )
        if not r.ok:
            return
        data = r.json()
        ts = (
            data.get("archived_snapshots", {})
            .get("closest", {})
            .get("timestamp")
        )
        if ts and len(ts) >= 8:
            d = datetime.strptime(ts[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
            sig.wayback_last_snapshot_days = (datetime.now(timezone.utc) - d).days
    except Exception as e:  # noqa: BLE001
        sig.errors.append(f"wb:{type(e).__name__}")


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------


def collect_one(row: dict[str, str], sess: requests.Session) -> Signals:
    sig = Signals(
        name=row["name"],
        website=row["website"],
        category=row.get("category", ""),
        founded=row.get("founded", ""),
        checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    note = row.get("notes", "").strip()
    if note:
        sig.notes.append(note)

    html = check_website(sig, sess)
    check_feed(sig, sess, html)
    check_github(sig, sess, row.get("github_org", "").strip())
    check_careers(sig, sess)
    check_wayback(sig, sess)
    return sig


def collect_all(input_csv: str) -> list[Signals]:
    with open(input_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    sess = _session()
    out: list[Signals] = []
    for i, row in enumerate(rows, 1):
        print(f"[{i}/{len(rows)}] {row['name']}", file=sys.stderr)
        try:
            out.append(collect_one(row, sess))
        except Exception as e:  # noqa: BLE001
            print(f"  ! unexpected: {e}", file=sys.stderr)
            out.append(Signals(
                name=row["name"],
                website=row.get("website", ""),
                category=row.get("category", ""),
                errors=[f"fatal:{type(e).__name__}"],
                checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ))
        time.sleep(0.5)  # be polite
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _apply_live_verified(signals: list, path: str = "data/live_verified.json") -> int:
    """Overlay human-verified snapshots on top of scraper output.

    live_verified.json holds signal values that were cross-checked via direct
    browser navigation + independent press coverage (see build_dashboard.py for
    the 'VERIFIED ...' note convention). Because the overlay records interpreted
    ground truth (e.g. Humane's 301 redirect to hp-iq.com, Argo's unreachable
    domain, Olive's redirect to Waystar), it replaces the raw scraper values
    for the listed companies. The verified_note is appended to sig.notes — the
    dashboard counts rows carrying one of those notes as '✓ verified'.

    Returns the number of rows updated. Safe to call even if the file is
    missing — it just no-ops.
    """
    try:
        with open(path, encoding="utf-8") as f:
            live = (json.load(f) or {}).get("verifications", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return 0
    if not live:
        return 0

    updated = 0
    for sig in signals:
        v = live.get(sig.name)
        if not v:
            continue
        sig.http_status = v.get("http_status")
        sig.ssl_ok = sig.http_status is not None and 200 <= (sig.http_status or 0) < 400
        sig.wayback_last_snapshot_days = v.get("wayback_days")
        sig.feed_last_post_days = v.get("feed_days")
        sig.github_commits_90d = v.get("github_commits_90d")
        sig.careers_page_found = v.get("careers_page_found")
        sig.jobs_detected = v.get("jobs_detected")
        note = v.get("verified_note")
        if note and note not in sig.notes:
            sig.notes.append(note)
        updated += 1
    return updated


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="AI Startup Survival Tracker signal collector")
    p.add_argument("--input", default="data/startups.csv")
    p.add_argument("--output", default="output/signals.json")
    p.add_argument("--verified", default="data/live_verified.json",
                   help="Human-verified overlay applied after scraping "
                        "(default: data/live_verified.json). Pass 'none' to skip.")
    args = p.parse_args(argv)

    signals = collect_all(args.input)

    # Apply the human-verified overlay BEFORE scoring so the verified
    # values feed directly into the weighted sum.
    if args.verified and args.verified.lower() != "none":
        n_verified = _apply_live_verified(signals, args.verified)
        if n_verified:
            print(f"Applied verified overlay to {n_verified} rows from {args.verified}")

    # Score after collection (import here to keep tracker.py standalone-runnable)
    from scoring import score_all
    score_all(signals)

    data = [asdict(s) for s in signals]
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote {len(data)} records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
