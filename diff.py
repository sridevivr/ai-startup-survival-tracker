"""
Delta report between two weekly snapshots.

Given two snapshot directories (produced by `snapshot.py`), write a
markdown report to `snapshots/diffs/<to_date>.md` covering:

    * Status changes (who moved bucket — "Watchlist → Likely Dead" etc).
      Sorted by severity: deaths first, then demotions, then promotions.
    * Biggest score movers (top N down, top N up) among rows whose status
      did NOT change — the quieter movers are often the more interesting
      ones.
    * New entries (appeared in the newer snapshot).
    * Dropped entries (in the prior snapshot, absent now).
    * Summary distribution delta (counts per status, prior → current).

Identity is the normalized website (with normalized name as fallback) —
same key snapshot.py writes as `normalized_website` into history.csv.

Design notes:

  - Status changes are prioritized over numeric moves because the status
    bucket is the decision-relevant unit. A 20-point slide that stays in
    Watchlist is less interesting than a 5-point slide that tips Healthy
    into Watchlist.
  - Not every signal change is meaningful. A 2-point drift on a noisy
    signal is noise, not news. The `--min-move` threshold (default 5)
    filters the "biggest movers" list down to changes worth looking at.
  - A "death" is defined as entering "Likely Dead" OR "Pivoted /
    Absorbed", which keeps acquihires from being overlooked just because
    they aren't literally shutdowns.

CLI:
    # default: compare the two newest dated snapshots in snapshots/
    python diff.py

    # explicit pair
    python diff.py --from 2026-04-22 --to 2026-04-29

    # tune what counts as a mover
    python diff.py --min-move 3 --top-n 20
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from urllib.parse import urlparse


DEATH_STATUSES = {"Likely Dead", "Pivoted / Absorbed"}
STATUS_ORDER = [
    "Thriving", "Healthy", "Watchlist", "Dormant",
    "Likely Dead", "Pivoted / Absorbed", "Not Yet Enriched",
]
# Higher index = worse outcome for promotion/demotion ranking.
STATUS_RANK = {s: i for i, s in enumerate(STATUS_ORDER)}


def _normalize_website(url: str | None) -> str:
    if not url:
        return ""
    url = url.strip()
    if not url:
        return ""
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
    host = _normalize_website(row.get("website"))
    if host:
        return host
    return (row.get("name") or "").strip().lower()


def _index(rows: list[dict]) -> dict[str, dict]:
    return {_identity(r): r for r in rows if _identity(r)}


def _list_dated_snapshots(root: str) -> list[str]:
    """Return sorted list of YYYY-MM-DD directory names under root."""
    if not os.path.isdir(root):
        return []
    pat = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    return sorted(d for d in os.listdir(root)
                  if pat.match(d) and os.path.isdir(os.path.join(root, d)))


def _load_snapshot(path: str) -> list[dict]:
    full = os.path.join(path, "signals.json")
    with open(full, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise SystemExit(f"{full} is not a list of signal objects")
    return data


def _severity(prior_status: str, current_status: str) -> int:
    """Lower number = more severe (deaths rank first).

    Bucket:
      0 = entered a death status
      1 = moved down at least one bucket (demotion)
      2 = moved up at least one bucket (promotion)
      3 = unchanged (not reported in status-change section)
    """
    if current_status in DEATH_STATUSES and prior_status not in DEATH_STATUSES:
        return 0
    pr = STATUS_RANK.get(prior_status, 99)
    cr = STATUS_RANK.get(current_status, 99)
    if cr > pr:
        return 1
    if cr < pr:
        return 2
    return 3


def _fmt_score(v) -> str:
    if v is None or v == "":
        return "—"
    try:
        return f"{float(v):.1f}"
    except (TypeError, ValueError):
        return str(v)


def _score_delta(prior, current) -> float | None:
    try:
        return float(current) - float(prior)
    except (TypeError, ValueError):
        return None


def build_diff(
    prior_rows: list[dict],
    current_rows: list[dict],
    from_date: str,
    to_date: str,
    min_move: float,
    top_n: int,
) -> str:
    prior_idx = _index(prior_rows)
    current_idx = _index(current_rows)

    prior_keys = set(prior_idx)
    current_keys = set(current_idx)

    new_keys = current_keys - prior_keys
    dropped_keys = prior_keys - current_keys
    common_keys = current_keys & prior_keys

    # ---- Status changes ------------------------------------------------
    status_changes = []
    for k in common_keys:
        p, c = prior_idx[k], current_idx[k]
        p_stat, c_stat = p.get("status", ""), c.get("status", "")
        if p_stat != c_stat:
            status_changes.append({
                "name": c.get("name") or p.get("name") or k,
                "website": c.get("website") or p.get("website", ""),
                "from": p_stat,
                "to": c_stat,
                "score_from": p.get("survival_score"),
                "score_to": c.get("survival_score"),
                "severity": _severity(p_stat, c_stat),
            })
    status_changes.sort(key=lambda r: (r["severity"], r["name"].lower()))

    # ---- Biggest score movers (status-unchanged rows only) -------------
    movers = []
    for k in common_keys:
        p, c = prior_idx[k], current_idx[k]
        if p.get("status") != c.get("status"):
            continue  # already covered in status_changes
        delta = _score_delta(p.get("survival_score"), c.get("survival_score"))
        if delta is None:
            continue
        if abs(delta) < min_move:
            continue
        movers.append({
            "name": c.get("name") or p.get("name") or k,
            "website": c.get("website") or p.get("website", ""),
            "status": c.get("status", ""),
            "score_from": p.get("survival_score"),
            "score_to": c.get("survival_score"),
            "delta": delta,
        })
    down_movers = sorted([m for m in movers if m["delta"] < 0],
                         key=lambda m: m["delta"])[:top_n]
    up_movers = sorted([m for m in movers if m["delta"] > 0],
                       key=lambda m: -m["delta"])[:top_n]

    # ---- New / dropped -------------------------------------------------
    new_rows = sorted(
        (current_idx[k] for k in new_keys),
        key=lambda r: (r.get("name") or "").lower(),
    )
    dropped_rows = sorted(
        (prior_idx[k] for k in dropped_keys),
        key=lambda r: (r.get("name") or "").lower(),
    )

    # ---- Distribution delta -------------------------------------------
    def _dist(rows: list[dict]) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in rows:
            out[r.get("status", "")] = out.get(r.get("status", ""), 0) + 1
        return out

    dist_prior = _dist(prior_rows)
    dist_current = _dist(current_rows)
    all_statuses = sorted(
        set(dist_prior) | set(dist_current),
        key=lambda s: STATUS_RANK.get(s, 99),
    )

    # ---- Render ---------------------------------------------------------
    lines: list[str] = []
    lines.append(f"# Weekly delta report — {from_date} → {to_date}")
    lines.append("")
    lines.append(
        f"Comparing {len(prior_rows)} → {len(current_rows)} companies. "
        f"{len(status_changes)} status changes, {len(new_rows)} new, "
        f"{len(dropped_rows)} dropped, {len(down_movers) + len(up_movers)} "
        f"score moves ≥ {min_move} points."
    )
    lines.append("")

    # Distribution
    lines.append("## Distribution")
    lines.append("")
    lines.append("| Status | Prior | Current | Δ |")
    lines.append("|---|---:|---:|---:|")
    for s in all_statuses:
        p = dist_prior.get(s, 0)
        c = dist_current.get(s, 0)
        d = c - p
        sign = "+" if d > 0 else ""
        lines.append(f"| {s or '—'} | {p} | {c} | {sign}{d} |")
    lines.append("")

    # Status changes
    lines.append("## Status changes")
    lines.append("")
    if not status_changes:
        lines.append("_No status changes this week._")
    else:
        lines.append("| Company | Prior | Current | Score |")
        lines.append("|---|---|---|---|")
        for row in status_changes:
            lines.append(
                f"| {row['name']} | {row['from']} | **{row['to']}** | "
                f"{_fmt_score(row['score_from'])} → {_fmt_score(row['score_to'])} |"
            )
    lines.append("")

    # Movers
    lines.append(f"## Biggest score drops (status unchanged, Δ ≤ −{min_move})")
    lines.append("")
    if not down_movers:
        lines.append("_No significant drops this week._")
    else:
        lines.append("| Company | Status | Score | Δ |")
        lines.append("|---|---|---|---:|")
        for m in down_movers:
            lines.append(
                f"| {m['name']} | {m['status']} | "
                f"{_fmt_score(m['score_from'])} → {_fmt_score(m['score_to'])} | "
                f"{m['delta']:+.1f} |"
            )
    lines.append("")

    lines.append(f"## Biggest score gains (status unchanged, Δ ≥ +{min_move})")
    lines.append("")
    if not up_movers:
        lines.append("_No significant gains this week._")
    else:
        lines.append("| Company | Status | Score | Δ |")
        lines.append("|---|---|---|---:|")
        for m in up_movers:
            lines.append(
                f"| {m['name']} | {m['status']} | "
                f"{_fmt_score(m['score_from'])} → {_fmt_score(m['score_to'])} | "
                f"+{m['delta']:.1f} |"
            )
    lines.append("")

    # New / dropped
    lines.append("## New entries")
    lines.append("")
    if not new_rows:
        lines.append("_No new companies this week._")
    else:
        lines.append("| Company | Status | Score | Website |")
        lines.append("|---|---|---|---|")
        for r in new_rows:
            lines.append(
                f"| {r.get('name', '—')} | {r.get('status', '—')} | "
                f"{_fmt_score(r.get('survival_score'))} | "
                f"{r.get('website', '—')} |"
            )
    lines.append("")

    lines.append("## Dropped entries")
    lines.append("")
    if not dropped_rows:
        lines.append("_No companies dropped this week._")
    else:
        lines.append("| Company | Prior status | Prior score | Website |")
        lines.append("|---|---|---|---|")
        for r in dropped_rows:
            lines.append(
                f"| {r.get('name', '—')} | {r.get('status', '—')} | "
                f"{_fmt_score(r.get('survival_score'))} | "
                f"{r.get('website', '—')} |"
            )
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description="Diff two weekly snapshots.")
    p.add_argument("--root", default="snapshots",
                   help="Snapshot root directory (default: snapshots)")
    p.add_argument("--from", dest="from_date", default=None,
                   help="Prior snapshot date YYYY-MM-DD (default: second newest)")
    p.add_argument("--to", dest="to_date", default=None,
                   help="Current snapshot date YYYY-MM-DD (default: newest)")
    p.add_argument("--min-move", type=float, default=5.0,
                   help="Minimum absolute score delta to report as a 'mover' (default: 5.0)")
    p.add_argument("--top-n", type=int, default=15,
                   help="How many movers to list in each direction (default: 15)")
    p.add_argument("--out", default=None,
                   help="Output path (default: snapshots/diffs/<to_date>.md)")
    args = p.parse_args()

    dated = _list_dated_snapshots(args.root)
    if args.from_date is None or args.to_date is None:
        if len(dated) < 2:
            raise SystemExit(
                f"Need at least 2 dated snapshots in {args.root}/ to diff; "
                f"found {len(dated)}: {dated}. Run snapshot.py again next week "
                f"— or pass --from/--to explicitly for testing."
            )
        args.from_date = args.from_date or dated[-2]
        args.to_date = args.to_date or dated[-1]

    prior_dir = os.path.join(args.root, args.from_date)
    current_dir = os.path.join(args.root, args.to_date)
    for d in (prior_dir, current_dir):
        if not os.path.isdir(d):
            raise SystemExit(f"Missing snapshot directory: {d}")

    prior_rows = _load_snapshot(prior_dir)
    current_rows = _load_snapshot(current_dir)

    report = build_diff(
        prior_rows, current_rows,
        from_date=args.from_date, to_date=args.to_date,
        min_move=args.min_move, top_n=args.top_n,
    )

    out_path = args.out or os.path.join(args.root, "diffs", f"{args.to_date}.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
