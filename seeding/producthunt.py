"""Pull AI-tagged product launches from Product Hunt.

Product Hunt is our second seed source. It biases toward consumer-facing
products with good marketing — which is a useful complement to YC's bias
toward accelerator-backed B2B startups. Crucially, launching on PH is often
the canonical "day 1" timestamp for a consumer AI product, so PH gives us
cleaner launch dates than almost anything else.

## Two modes

**1. Public mode (default, no auth):** navigate PH's topic pages and extract
the inline Apollo SSR cache. This does not require any credentials. It is
brittle to PH UI changes and — critically — does NOT expose external
website URLs (PH hides them behind a click-through redirector for referral
tracking). So the public mode emits (name, slug, tagline, launchedAt,
score) and leaves the `website` column empty; the downstream enricher
follows individual product pages to resolve it.

**2. API mode (if PH_TOKEN set):** use PH's GraphQL v2 API with an OAuth
app token. The PH GraphQL API exposes `website` directly. This requires:
    1. Register an app at https://www.producthunt.com/v2/oauth/applications
    2. Use client_credentials flow to get a token
    3. Set PH_TOKEN env var before running this script

## Why no authenticated mode by default

Forcing a user through OAuth registration just to seed a list is a UX
speedbump. Public mode is good enough to validate the adapter; users who
want the full dataset with websites can opt in to API mode with one env
var.

Run:
    python seeding/producthunt.py --out seeding/sources/producthunt.csv
    # or with auth:
    PH_TOKEN=xxx python seeding/producthunt.py --mode api
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Iterable

TOPIC_URL = "https://www.producthunt.com/topics/{slug}?popular=true"
GRAPHQL_URL = "https://api.producthunt.com/v2/api/graphql"

# PH topic slugs that are AI-adjacent. Querying a mix of these gives better
# coverage than any single topic — "artificial-intelligence" skews toward
# meta tools; "generative-ai" captures the actual startup cohort.
DEFAULT_TOPICS = [
    "artificial-intelligence",
    "generative-ai",
    "ai-agents",
]

# Default minimum launch date. The tracker covers the 2023+ AI wave, so
# rows older than this (or with missing launch dates — which on PH usually
# means they're evergreen brands like Figma, Stripe, Slack that just happen
# to appear on AI topic pages) are dropped. Override with --min-date.
DEFAULT_MIN_DATE = "2023-01-01"

CSV_FIELDS = [
    "name", "website", "ph_slug", "tagline", "launched_at",
    "score", "source",
]

USER_AGENT = "ai-startup-survival-tracker-seeder/1.0"


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_apollo_from_html(html: str) -> dict:
    """Extract the Apollo SSRDataTransport payload from PH's HTML.

    PH inlines a stream of Apollo cache entries in a <script> tag. The
    payload is pushed into a shared buffer:
        (window[Symbol.for("ApolloSSRDataTransport")] ??= []).push({...})

    We regex-match each push and merge.
    """
    pattern = re.compile(
        r'ApolloSSRDataTransport"\)\]\s*\?\?=\s*\[\]\)\.push\((\{.*?\})\);',
        re.DOTALL,
    )
    merged: dict = {}
    for m in pattern.finditer(html):
        try:
            chunk = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        # Chunks contain 'rehydrate' and/or 'results' keys. We want whatever
        # has Product/Post typename entries.
        for k, v in (chunk.get("rehydrate") or {}).items():
            merged[k] = v
        for r in (chunk.get("results") or []):
            data = (r or {}).get("result", {}).get("data")
            if data:
                for k, v in data.items():
                    merged[f"result_{k}"] = v
    return merged


def posts_from_cache(cache: dict) -> list[dict]:
    """Find all Post + linked Product entries in the merged cache.

    PH's cache has Posts (launches) linked to Products (the parent brand).
    A product can have multiple launches; we keep the earliest. We walk
    every cache entry whose JSON form contains typename markers.
    """
    # The cache keys from SSR are opaque ("_R_xxx_"). We dig into .data
    # values to find Product/Post objects by their __typename.
    posts_by_id: dict[str, dict] = {}
    products_by_id: dict[str, dict] = {}

    def walk(o):
        if isinstance(o, dict):
            t = o.get("__typename")
            if t == "Post" and "slug" in o:
                posts_by_id[o["id"]] = o
            elif t == "Product" and "slug" in o:
                products_by_id[o["id"]] = o
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(cache)

    out: list[dict] = []
    seen_products: dict[str, dict] = {}
    for post in posts_by_id.values():
        product_ref = post.get("product") or {}
        # Ref might be {"__ref": "ProductNNNN"} or the inlined product
        if "__ref" in product_ref:
            prod = products_by_id.get(product_ref["__ref"].split(":")[-1]) \
                   or products_by_id.get(product_ref["__ref"].replace("Product", ""))
        else:
            prod = product_ref
        if not prod:
            continue
        row = {
            "ph_slug": prod.get("slug"),
            "name": prod.get("name") or post.get("name"),
            "tagline": prod.get("tagline", ""),
            "launched_at": (post.get("createdAt") or "")[:10],
            "score": post.get("latestScore") or 0,
        }
        if not row["ph_slug"]:
            continue
        prev = seen_products.get(row["ph_slug"])
        if prev is None or (row["launched_at"] and prev["launched_at"] and row["launched_at"] < prev["launched_at"]):
            seen_products[row["ph_slug"]] = row
    return list(seen_products.values())


def pull_public(topics: Iterable[str]) -> list[dict]:
    rows: list[dict] = []
    seen = set()
    for topic in topics:
        url = TOPIC_URL.format(slug=topic)
        print(f"  fetching {url}", file=sys.stderr)
        try:
            html = _fetch(url)
        except urllib.error.URLError as e:
            print(f"    ! {e}", file=sys.stderr)
            continue
        cache = parse_apollo_from_html(html)
        for r in posts_from_cache(cache):
            if r["ph_slug"] in seen:
                continue
            seen.add(r["ph_slug"])
            rows.append({
                "name": r["name"],
                "website": "",  # public mode can't resolve this — see module docstring
                "ph_slug": r["ph_slug"],
                "tagline": r["tagline"],
                "launched_at": r["launched_at"],
                "score": r["score"],
                "source": "producthunt",
            })
    return rows


def pull_api(topics: Iterable[str], token: str) -> list[dict]:
    """Pull via the authenticated GraphQL API — this one can resolve website."""
    rows: list[dict] = []
    seen = set()
    query = """
    query TopicPosts($slug: String!, $after: String) {
      topic(slug: $slug) {
        posts(first: 50, after: $after, order: VOTES) {
          pageInfo { hasNextPage endCursor }
          edges { node {
            id name slug tagline website createdAt votesCount
          } }
        }
      }
    }
    """
    for topic in topics:
        after = None
        for _ in range(5):  # cap pages
            body = {"query": query, "variables": {"slug": topic, "after": after}}
            req = urllib.request.Request(
                GRAPHQL_URL,
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "User-Agent": USER_AGENT,
                },
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
            conn = ((data or {}).get("data") or {}).get("topic", {}).get("posts", {}) or {}
            for e in conn.get("edges", []):
                n = e["node"]
                slug = n.get("slug")
                if not slug or slug in seen:
                    continue
                seen.add(slug)
                rows.append({
                    "name": n.get("name", ""),
                    "website": n.get("website", ""),
                    "ph_slug": slug,
                    "tagline": n.get("tagline", ""),
                    "launched_at": (n.get("createdAt") or "")[:10],
                    "score": n.get("votesCount", 0),
                    "source": "producthunt",
                })
            info = conn.get("pageInfo", {})
            if not info.get("hasNextPage"):
                break
            after = info.get("endCursor")
    return rows


def write_csv(rows: list[dict], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)


def filter_by_date(rows: list[dict], min_date: str) -> list[dict]:
    """Keep rows whose launched_at is present and >= min_date (YYYY-MM-DD).

    Empty launched_at values are DROPPED. On PH, a missing launch date is a
    strong signal that the entry is a long-running brand (Figma, Stripe, Slack
    etc.) that surfaces on AI topic pages via tagging but isn't a 2023+ AI
    startup. Dropping them is the whole point of this filter.
    """
    kept: list[dict] = []
    for r in rows:
        launched = (r.get("launched_at") or "").strip()
        if len(launched) >= 10 and launched[:10] >= min_date:
            kept.append(r)
    return kept


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="seeding/sources/producthunt.csv")
    ap.add_argument("--mode", choices=["public", "api"], default="public")
    ap.add_argument("--topics", nargs="*", default=DEFAULT_TOPICS)
    ap.add_argument("--min-date", default=DEFAULT_MIN_DATE,
                    help="Drop rows launched before this ISO date "
                         "(YYYY-MM-DD). Also drops rows with no launch date. "
                         "Set to 1900-01-01 to disable.")
    args = ap.parse_args()

    print(f"Pulling PH topics={args.topics} mode={args.mode}", file=sys.stderr)
    if args.mode == "api":
        token = os.environ.get("PH_TOKEN")
        if not token:
            print("ERROR: PH_TOKEN env var required for --mode api",
                  file=sys.stderr)
            return 2
        rows = pull_api(args.topics, token)
    else:
        rows = pull_public(args.topics)

    before = len(rows)
    rows = filter_by_date(rows, args.min_date)
    dropped = before - len(rows)
    if dropped:
        print(f"  filtered out {dropped} rows launched before "
              f"{args.min_date} (or with no launch date)", file=sys.stderr)

    write_csv(rows, args.out)

    missing_site = sum(1 for r in rows if not r["website"])
    print(f"Wrote {len(rows)} rows to {args.out}", file=sys.stderr)
    print(f"  (missing website: {missing_site} — expected in public mode)",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
