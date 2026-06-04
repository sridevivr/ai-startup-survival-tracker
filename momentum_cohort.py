"""Step 1 of the YC AI Momentum Heatmap pivot.

Reads:
    data/startups.csv      — 578 YC AI startups (name, website, founded, sector, function, ...)
    output/signals.json    — 35 signal fields per company

Writes:
    data/master.csv        — ~144 surviving companies × 9 columns
                              (name, website, founded_year, sector, sub-sector,
                               functionality, funding, signals, notes)

Cut rules:
    1. founded_year >= 2023            (post-ChatGPT cohort)
    2. status not in {Likely Dead, Pivoted / Absorbed, Dormant}
    3. >= 1 positive momentum signal
       (positive = recent news / fresh site / hiring / fresh blog / active github)
"""
from __future__ import annotations

import csv
import json
import os
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
STARTUPS_CSV = os.path.join(ROOT, "data", "startups.csv")
SIGNALS_JSON = os.path.join(ROOT, "output", "signals.json")
MASTER_CSV = os.path.join(ROOT, "data", "master.csv")

CUT_STATUSES = {"Likely Dead", "Pivoted / Absorbed", "Dormant"}

MASTER_COLUMNS = [
    "name", "website", "founded_year",
    "sector", "sub-sector", "functionality",
    "funding", "signals", "notes",
]


def positive_signals(sig: dict) -> dict[str, bool]:
    """Five positive-momentum checks. Each True/False."""
    return {
        "news": (sig.get("news_item_count_180d") or 0) >= 1,
        "fresh_site": (sig.get("wayback_last_snapshot_days") or 9999) <= 90,
        "hiring": (sig.get("jobs_detected") or 0) >= 1,
        "fresh_blog": (sig.get("feed_last_post_days") or 9999) <= 90,
        "github": (sig.get("github_commits_90d") or 0) >= 5,
    }


def signal_summary(sig: dict) -> str:
    """Compact human-readable view of firing positive signals.

    Example: "news:3 hiring:5 wayback:45d"
    Empty string if nothing fires (shouldn't happen post-cut).
    """
    parts: list[str] = []
    n_news = sig.get("news_item_count_180d") or 0
    if n_news >= 1:
        parts.append(f"news:{n_news}")
    wayback = sig.get("wayback_last_snapshot_days")
    if wayback is not None and wayback <= 90:
        parts.append(f"wayback:{wayback}d")
    jobs = sig.get("jobs_detected") or 0
    if jobs >= 1:
        parts.append(f"hiring:{jobs}")
    blog = sig.get("feed_last_post_days")
    if blog is not None and blog <= 90:
        parts.append(f"blog:{blog}d")
    gh = sig.get("github_commits_90d") or 0
    if gh >= 5:
        parts.append(f"github:{gh}/90d")
    return " ".join(parts)


def load_signals() -> dict[str, dict]:
    with open(SIGNALS_JSON, encoding="utf-8") as f:
        records = json.load(f)
    return {r["name"]: r for r in records}


def main() -> None:
    sigs = load_signals()

    with open(STARTUPS_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    total = len(rows)

    # Stage 1: founded >= 2023
    rows = [r for r in rows
            if (r.get("founded") or "").strip().isdigit()
            and int(r["founded"]) >= 2023]
    after_year = len(rows)

    # Stage 2: cut dead/pivoted/dormant
    cut_status: Counter[str] = Counter()
    kept: list[dict] = []
    for r in rows:
        sig = sigs.get(r["name"], {})
        st = sig.get("status", "")
        if st in CUT_STATUSES:
            cut_status[st] += 1
            continue
        kept.append(r)
    rows = kept
    after_status = len(rows)

    # Stage 3: >= 1 positive signal
    rows = [r for r in rows
            if sum(positive_signals(sigs.get(r["name"], {})).values()) >= 1]
    after_signals = len(rows)

    # Build master.csv records
    out_rows: list[dict] = []
    for r in rows:
        sig = sigs.get(r["name"], {})
        out_rows.append({
            "name": r["name"],
            "website": r.get("website", ""),
            "founded_year": r.get("founded", ""),
            "sector": r.get("sector", ""),
            "sub-sector": "",  # filled in Step 4
            "functionality": r.get("function", ""),
            "funding": "",  # filled in Step 3
            "signals": signal_summary(sig),
            "notes": r.get("notes", ""),
        })

    # Sort: by sector, then functionality, then name — easy to scan
    out_rows.sort(key=lambda x: (x["sector"], x["functionality"], x["name"]))

    os.makedirs(os.path.dirname(MASTER_CSV), exist_ok=True)
    with open(MASTER_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MASTER_COLUMNS)
        w.writeheader()
        w.writerows(out_rows)

    # Report
    print(f"Cohort filter results")
    print(f"  Total startups in source:                       {total}")
    print(f"  After founded >= 2023:                          {after_year}")
    print(f"  After cutting dead/pivoted/dormant:             {after_status}")
    for st, n in cut_status.most_common():
        print(f"    (cut {n}× {st})")
    print(f"  After cutting zero-positive-signal companies:   {after_signals}")
    print()
    print(f"Wrote {len(out_rows)} rows to {MASTER_CSV}")
    print()

    # Distribution by sector × functionality
    matrix: Counter[tuple[str, str]] = Counter()
    sector_n: Counter[str] = Counter()
    func_n: Counter[str] = Counter()
    for r in out_rows:
        s = r["sector"] or "—"
        f = r["functionality"] or "—"
        matrix[(s, f)] += 1
        sector_n[s] += 1
        func_n[f] += 1

    print("Top 10 (sector × functionality) cells by count:")
    for (s, f), n in matrix.most_common(10):
        print(f"  {n:>3}  {s} × {f}")
    print()
    print("By sector:")
    for s, n in sector_n.most_common():
        print(f"  {n:>3}  {s}")
    print()
    print("By functionality:")
    for f, n in func_n.most_common():
        print(f"  {n:>3}  {f}")


if __name__ == "__main__":
    main()
