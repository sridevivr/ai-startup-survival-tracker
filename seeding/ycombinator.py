"""Pull AI-tagged companies from Y Combinator's public directory.

YC's directory is powered by Algolia. The public Application ID and a
restricted search API key are embedded in the page HTML at
https://www.ycombinator.com/companies — anyone loading that page receives
them. That means the query is reproducible without any scraping of rendered
HTML: we hit Algolia directly.

The two parameters worth tweaking:
  - TAGS: which tag(s) qualify a company as AI. YC uses both "Artificial
    Intelligence" and "AI" as tags; we filter for the former which is the
    canonical label (539 hits for 2023-2025 batches at time of writing).
  - BATCHES: which YC cohorts to include. The 2023-2025 AI cohort is the
    cleanest slice for a survival tracker — the oldest batches have had
    enough time to sort winners from losers.

Run:
    python seeding/ycombinator.py --out seeding/sources/yc.csv

The Algolia credentials below are public (anyone can fetch them from the YC
directory page), and YC has authorized this index for client-side queries.
They may rotate — if the script returns 0 hits, re-fetch them by loading
https://www.ycombinator.com/companies in a browser and grepping the page
source for `AlgoliaOpts`.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.parse
import urllib.request
from typing import Iterable

ALGOLIA_APP = "45BWZJ1SGC"
# Public search key scoped to the YC company index — visible in page HTML.
ALGOLIA_KEY = (
    "NzllNTY5MzJiZGM2OTY2ZTQwMDEzOTNhYWZiZGRjODlh"
    "YzVkNjBmOGRjNzJiMWM4ZTU0ZDlhYTZjOTJiMjlhMWFu"
    "YWx5dGljc1RhZ3M9eWNkYyZyZXN0cmljdEluZGljZXM9"
    "WUNDb21wYW55X3Byb2R1Y3Rpb24lMkNZQ0NvbXBhbnlf"
    "QnlfTGF1bmNoX0RhdGVfcHJvZHVjdGlvbiZ0YWdGaWx0"
    "ZXJzPSU1QiUyMnljZGNfcHVibGljJTIyJTVE"
)
ALGOLIA_URL = f"https://{ALGOLIA_APP}-dsn.algolia.net/1/indexes/*/queries"

# Canonical tag to filter on. "Artificial Intelligence" is YC's primary AI
# tag; "AI" and "Generative AI" also exist but are narrower subsets.
DEFAULT_TAGS = ["Artificial Intelligence"]

# 2023-2025 cohorts — the slice that has had time to either ship or die.
DEFAULT_BATCHES = [
    "Winter 2023", "Summer 2023",
    "Winter 2024", "Summer 2024", "Fall 2024",
    "Winter 2025", "Spring 2025", "Summer 2025", "Fall 2025",
]

CSV_FIELDS = [
    "name", "website", "batch", "status", "founded_year",
    "team_size", "one_liner", "yc_slug", "source",
]


def algolia_query(
    tags: Iterable[str],
    batches: Iterable[str],
    page: int,
    hits_per_page: int = 100,
) -> dict:
    """Build the Algolia request body for one page."""
    facet_filters = [
        [f"tags:{t}" for t in tags],
        [f"batch:{b}" for b in batches],
    ]
    params = urllib.parse.urlencode({
        "query": "",
        "hitsPerPage": hits_per_page,
        "page": page,
        "facetFilters": json.dumps(facet_filters),
    })
    return {
        "requests": [{
            "indexName": "YCCompany_production",
            "params": params,
        }]
    }


def fetch_page(body: dict) -> dict:
    """POST the body to Algolia and return the parsed JSON response."""
    req = urllib.request.Request(
        ALGOLIA_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "X-Algolia-Application-Id": ALGOLIA_APP,
            "X-Algolia-API-Key": ALGOLIA_KEY,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def pull_all(tags: Iterable[str], batches: Iterable[str]) -> list[dict]:
    """Pull every matching company across all pages."""
    all_hits: list[dict] = []
    for page in range(20):  # hard stop after 20 pages (~2000 hits)
        body = algolia_query(tags, batches, page)
        data = fetch_page(body)
        result = data.get("results", [{}])[0]
        hits = result.get("hits", [])
        all_hits.extend(hits)
        if len(hits) < 100:
            break
    return all_hits


def row_for(hit: dict) -> dict:
    """Flatten one Algolia hit into our CSV row shape."""
    launched_at = hit.get("launched_at")
    founded_year = ""
    if isinstance(launched_at, (int, float)) and launched_at > 0:
        import datetime
        founded_year = datetime.datetime.fromtimestamp(launched_at).year
    return {
        "name": hit.get("name", ""),
        "website": hit.get("website", ""),
        "batch": hit.get("batch", ""),
        "status": hit.get("status", ""),
        "founded_year": founded_year,
        "team_size": hit.get("team_size") or "",
        "one_liner": (hit.get("one_liner") or "")[:200],
        "yc_slug": hit.get("slug", ""),
        "source": "ycombinator",
    }


def write_csv(rows: list[dict], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="seeding/sources/yc.csv",
                    help="Output CSV path")
    ap.add_argument("--tags", nargs="*", default=DEFAULT_TAGS,
                    help="Tags to include (OR)")
    ap.add_argument("--batches", nargs="*", default=DEFAULT_BATCHES,
                    help="Batches to include (OR)")
    ap.add_argument("--status-filter", nargs="*", default=None,
                    help="If set, keep only rows with these YC statuses "
                         "(Active, Inactive, Acquired)")
    args = ap.parse_args()

    print(f"Pulling tags={args.tags} batches={args.batches} ...",
          file=sys.stderr)
    hits = pull_all(args.tags, args.batches)
    print(f"  → {len(hits)} total hits", file=sys.stderr)

    rows = [row_for(h) for h in hits]
    if args.status_filter:
        rows = [r for r in rows if r["status"] in args.status_filter]
        print(f"  → {len(rows)} after status filter {args.status_filter}",
              file=sys.stderr)

    write_csv(rows, args.out)

    # Summary for the operator — batch + status breakdown is the most useful
    # quick-look signal ("how many of these are already flagged dead by YC?")
    from collections import Counter
    by_status = Counter(r["status"] for r in rows)
    by_batch = Counter(r["batch"] for r in rows)
    print(f"Wrote {len(rows)} rows to {args.out}", file=sys.stderr)
    print(f"  by status: {dict(by_status)}", file=sys.stderr)
    print(f"  by batch:  {dict(by_batch)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
