"""
Generate a realistic sample signals dataset WITHOUT hitting the live web.

This is used in demo / offline contexts where running tracker.py against the
live web is not possible. Values are curated from public reporting through
early 2025. For live data, run ``tracker.py`` directly.
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone

from tracker import Signals
from scoring import score_all


# --------------------------------------------------------------------------
# Curated snapshot — (website_200_ok, wayback_days, feed_days, github_commits_90d,
#                     careers_page, jobs_detected)
# Values are realistic estimates for demonstration. The real tool would
# populate these directly from the network.
# --------------------------------------------------------------------------

CURATED: dict[str, tuple] = {
    # Foundation model majors — all thriving, hiring aggressively
    "OpenAI":        (200, 3,  7,   None, True, 180),
    "Anthropic":     (200, 2,  5,   None, True, 210),
    "Mistral AI":    (200, 4,  14,  320,  True, 65),
    "xAI":           (200, 5,  21,  None, True, 55),
    "Cohere":        (200, 6,  18,  45,   True, 40),

    # AI Search / Consumer AI — Perplexity thriving
    "Perplexity":    (200, 3,  10,  None, True, 85),

    # Major pivots / acquihires (the original entity is effectively gone)
    "Character.AI":  (200, 8,  None, None, True, 5),   # Google licensing deal Aug 2024
    "Inflection AI": (200, 60, None, None, False, 0),  # MSFT acquihired Mar 2024
    "Adept":         (200, 45, None, None, False, 0),  # Amazon acquihired Jun 2024

    # Stressed but alive
    "Stability AI":  (200, 14, 95,  12,  True, 8),     # leadership turmoil, still shipping
    "Jasper":        (200, 10, 60,  None, True, 12),   # layoffs, still operating

    # Healthy / growing
    "Runway":        (200, 4,  18,  None, True, 38),
    "ElevenLabs":    (200, 3,  9,   180, True, 70),
    "Hugging Face":  (200, 1,  3,   900, True, 55),
    "Suno":          (200, 6,  22,  None, True, 28),
    "Midjourney":    (200, 5,  45,  None, False, 0),   # famously no job board
    "Glean":         (200, 7,  20,  None, True, 95),
    "Harvey":        (200, 5,  14,  None, True, 60),
    "Writer":        (200, 6,  12,  None, True, 45),
    "Synthesia":     (200, 4,  16,  None, True, 75),
    "Together AI":   (200, 3,  11,  240, True, 40),
    "Replicate":     (200, 4,  25,  150, True, 22),
    "Pika":          (200, 8,  35,  None, True, 18),
    "Luma AI":       (200, 5,  22,  None, True, 30),

    # Dead or effectively dead
    "Humane":        (200, 30, None, None, False, 0),  # HP acquisition Feb 2025 — entity gone
    "Rewind AI":     (301, 90, None, None, False, 0),  # redirects to Limitless
    "Forward Health":(200, 40, None, None, False, 0),  # CarePod shut down Nov 2024
    "Olive AI":      (None, 500, None, None, False, 0), # shut down Oct 2023
    "Argo AI":       (None, 800, None, None, False, 0), # shut down Oct 2022
    "Ghost Autonomy":(None, 300, None, None, False, 0), # shut down Apr 2024

    # Mid-market — varies
    "Typeface":      (200, 20, 180, None, True, 4),    # layoffs, Salesforce talks
    "Hippocratic AI":(200, 7,  35,  None, True, 42),
    "Sakana AI":     (200, 10, 28,  35,  True, 18),
    "Magic":         (200, 14, None, None, True, 15),
    "Poolside":      (200, 8,  45,  None, True, 25),
    "Codeium":       (200, 5,  20,  None, True, 55),   # rebranded to Windsurf
    "Cursor":        (200, 2,  12,  None, True, 48),
}


def _load_live_verified() -> dict:
    """Load the live-verified snapshot (captured via Claude-in-Chrome).
    These override curated values for the listed companies."""
    try:
        with open("data/live_verified.json", encoding="utf-8") as f:
            return json.load(f).get("verifications", {})
    except FileNotFoundError:
        return {}


def main() -> None:
    with open("data/startups.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    live = _load_live_verified()

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    signals: list[Signals] = []
    for row in rows:
        name = row["name"]
        curated = CURATED.get(name)
        sig = Signals(
            name=name,
            website=row["website"],
            category=row.get("category", ""),
            founded=row.get("founded", ""),
            checked_at=now,
        )
        note = row.get("notes", "").strip()
        if note:
            sig.notes.append(note)

        if curated is None:
            sig.errors.append("no_curated_data")
        else:
            http, wb, fd, gh, careers, jobs = curated
            sig.http_status = http
            sig.ssl_ok = http is not None and 200 <= (http or 0) < 400
            sig.homepage_bytes = 45000 if http and http < 400 else None
            sig.wayback_last_snapshot_days = wb
            sig.feed_last_post_days = fd
            sig.github_commits_90d = gh
            sig.careers_page_found = careers
            sig.jobs_detected = jobs if careers else None

        # Apply live-verified overrides where available
        if name in live:
            v = live[name]
            sig.http_status = v.get("http_status")
            sig.ssl_ok = sig.http_status is not None and 200 <= (sig.http_status or 0) < 400
            sig.wayback_last_snapshot_days = v.get("wayback_days")
            sig.feed_last_post_days = v.get("feed_days")
            sig.github_commits_90d = v.get("github_commits_90d")
            sig.careers_page_found = v.get("careers_page_found")
            sig.jobs_detected = v.get("jobs_detected")
            if v.get("verified_note"):
                sig.notes.append(v["verified_note"])

        signals.append(sig)

    score_all(signals)

    # Write JSON + a flat CSV for spreadsheet users
    out = [asdict(s) for s in signals]
    with open("output/signals.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    fields = [
        "name", "category", "founded", "status", "survival_score",
        "signal_coverage", "http_status", "wayback_last_snapshot_days",
        "feed_last_post_days", "github_commits_90d", "careers_page_found",
        "jobs_detected", "notes",
    ]
    with open("output/signals.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for s in out:
            row = {k: s.get(k) for k in fields}
            row["notes"] = "; ".join(s.get("notes") or [])
            w.writerow(row)

    # Summary to stderr
    from collections import Counter
    counts = Counter(s["status"] for s in out)
    print(f"Generated {len(out)} records.")
    for status, n in counts.most_common():
        print(f"  {status:20s} {n}")


if __name__ == "__main__":
    main()
