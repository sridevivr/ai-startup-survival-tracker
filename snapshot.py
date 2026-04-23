"""
Weekly snapshot writer for the AI Startup Survival Tracker.

Reads `output/signals.json` (the canonical current-state dataset) and:

    1. Copies the full JSON verbatim into `snapshots/YYYY-MM-DD/signals.json`
       — preserves every field so diffs can be exact and historical audits
       don't lose context (news headlines, notes, etc).
    2. Appends a tidy per-company row to `snapshots/history.csv` with the
       handful of columns that matter for time series:
           snapshot_date, name, normalized_website, status, survival_score,
           signal_coverage, website, category
       One row per (company, snapshot) — easy to load into pandas / sqlite
       / a spreadsheet without parsing JSON.

The dual-storage design is deliberate: the JSON is the fidelity layer, the
CSV is the queryability layer. `diff.py` reads the JSONs pairwise; any
analytics / charts / trends read the CSV.

Identity is the normalized website (lowercased host, no scheme, no `www.`,
no trailing slash). Name is a fallback when the website is missing. This
is the same key `seeding/merge.py` uses to dedupe — consistency matters so
the snapshot join works without surprises.

CLI:
    python snapshot.py                          # today's date
    python snapshot.py --date 2026-04-22        # explicit date (for backfill / tests)
    python snapshot.py --signals output/signals.json --out snapshots
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import shutil
import sys
from urllib.parse import urlparse


HISTORY_COLUMNS = [
    "snapshot_date",
    "name",
    "normalized_website",
    "status",
    "survival_score",
    "signal_coverage",
    "website",
    "category",
]


def _normalize_website(url: str | None) -> str:
    """Lowercase host without scheme / www. / trailing slash.

    Mirrors the normalization used by `seeding/merge.py` so snapshot rows
    join cleanly across weeks even if the underlying CSV gets re-emitted.
    """
    if not url:
        return ""
    url = url.strip()
    if not url:
        return ""
    # urlparse needs a scheme to populate netloc — coerce bare hosts.
    if "://" not in url:
        url = "http://" + url
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host.rstrip("/")


def _identity(row: dict) -> str:
    """Stable identity for a row. Prefer website; fall back to name."""
    host = _normalize_website(row.get("website"))
    if host:
        return host
    return (row.get("name") or "").strip().lower()


def _load_signals(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise SystemExit(f"{path} is not a list of signal objects")
    return data


def _write_json_snapshot(data: list[dict], snapshot_dir: str) -> str:
    os.makedirs(snapshot_dir, exist_ok=True)
    out_path = os.path.join(snapshot_dir, "signals.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    return out_path


def _append_history(data: list[dict], history_path: str, snapshot_date: str) -> int:
    """Append a tidy row per company to history.csv. Create with header if new."""
    os.makedirs(os.path.dirname(history_path) or ".", exist_ok=True)
    exists = os.path.exists(history_path)
    added = 0
    with open(history_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(HISTORY_COLUMNS)
        for row in data:
            w.writerow([
                snapshot_date,
                row.get("name", ""),
                _identity(row),
                row.get("status", ""),
                row.get("survival_score", ""),
                row.get("signal_coverage", ""),
                row.get("website", ""),
                row.get("category", ""),
            ])
            added += 1
    return added


def main() -> None:
    p = argparse.ArgumentParser(description="Write a weekly snapshot of signals.json.")
    p.add_argument("--signals", default="output/signals.json",
                   help="Path to current signals.json (default: output/signals.json)")
    p.add_argument("--out", default="snapshots",
                   help="Snapshot root directory (default: snapshots)")
    p.add_argument("--date", default=None,
                   help="Snapshot date in YYYY-MM-DD (default: today, UTC)")
    p.add_argument("--force", action="store_true",
                   help="Overwrite an existing snapshot for this date")
    args = p.parse_args()

    snapshot_date = args.date or dt.datetime.utcnow().strftime("%Y-%m-%d")
    # Sanity-check the date format.
    try:
        dt.datetime.strptime(snapshot_date, "%Y-%m-%d")
    except ValueError:
        raise SystemExit(f"--date must be YYYY-MM-DD, got: {snapshot_date}")

    if not os.path.exists(args.signals):
        raise SystemExit(f"No signals file at {args.signals}. Run tracker.py first.")

    data = _load_signals(args.signals)
    if not data:
        raise SystemExit(f"{args.signals} is empty — nothing to snapshot.")

    snapshot_dir = os.path.join(args.out, snapshot_date)
    if os.path.isdir(snapshot_dir) and not args.force:
        raise SystemExit(
            f"Snapshot already exists at {snapshot_dir}. "
            f"Use --force to overwrite (this will re-append history.csv rows too)."
        )
    if args.force and os.path.isdir(snapshot_dir):
        shutil.rmtree(snapshot_dir)

    json_path = _write_json_snapshot(data, snapshot_dir)

    history_path = os.path.join(args.out, "history.csv")
    # If we're forcing a re-snapshot, purge prior history rows for this date
    # so we don't double-count the day.
    if args.force and os.path.exists(history_path):
        _purge_history_date(history_path, snapshot_date)

    added = _append_history(data, history_path, snapshot_date)

    print(f"Snapshot written: {json_path}  ({len(data)} companies)")
    print(f"History updated:  {history_path}  (+{added} rows)")


def _purge_history_date(history_path: str, snapshot_date: str) -> None:
    """Remove any existing rows for `snapshot_date` from history.csv."""
    if not os.path.exists(history_path):
        return
    keep: list[list[str]] = []
    with open(history_path, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        header = next(r, None)
        if header is None:
            return
        for row in r:
            if row and row[0] != snapshot_date:
                keep.append(row)
    with open(history_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(keep)


if __name__ == "__main__":
    main()
