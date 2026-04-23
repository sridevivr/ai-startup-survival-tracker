"""
News signal collector — Google News RSS, no API key, no auth.
=============================================================

Google News exposes an RSS endpoint for search queries at
``https://news.google.com/rss/search?q=<query>``. That's it — the URL is
the whole contract. No token, no scraping. The feed returns up to ~100
items and each item includes a title, pubDate, link, and source.

We use this to answer three cheap questions for every tracked company:

  1. Has anyone in the press mentioned them at all in the last 6 months?
     (news_item_count_180d)
  2. When was the most recent mention?
     (news_last_mention_days)
  3. Does that recent coverage contain death markers ("shutting down",
     "lays off") or health markers ("raised Series B", "launches")?
     (news_death_signal / news_health_signal)

Running an LLM-powered agent to "read the news" is overkill for a
triage-level signal. Keyword matching on headlines catches the
load-bearing cases (shutdowns, funding rounds, acquisitions) and is
auditable — every flag traces back to a headline we can show in the UI.

Run:
    python tracker_news.py --input data/startups.csv --output output/news.json

Output format:
    {
      "Company Name": {
        "news_item_count_180d": 7,
        "news_last_mention_days": 12,
        "news_death_signal": false,
        "news_health_signal": true,
        "news_death_headline": "",
        "news_health_headline": "Company raises $20M Series A ...",
        "query_url": "https://news.google.com/rss/search?q=...",
        "checked_at": "2026-04-20T..."
      },
      ...
    }

Design notes:
  * Stdlib only. We already rely on urllib+json+csv elsewhere; keeping
    tracker_news.py dependency-free means it can run inside the scoring
    pipeline without additional installs.
  * One HTTP request per company, with a polite sleep between. At ~600
    companies and 1s sleep, a full pass is ~10 minutes.
  * Query is ``"<name>" (shutdown OR acquired OR layoffs OR funding OR
    raised)`` — the quoted name reduces false positives, and the
    keyword-disjunction boosts recall for the signals we care about.
  * News items are filtered to a 180-day window. Anything older is
    noise for a "still alive?" question.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional


RSS_URL = "https://news.google.com/rss/search"
USER_AGENT = "ai-startup-survival-tracker-news/1.0"
DEFAULT_TIMEOUT = 15
WINDOW_DAYS = 180

# Shared SSL context — set to an unverified one if --insecure is passed.
# macOS Python (python.org installer) ships without a system-wide CA bundle,
# so verification fails out of the box for many users. Proper fix is to run
# /Applications/Python\ 3.X/Install\ Certificates.command once; the escape
# hatch here is to accept that the target (Google News RSS) is a public
# endpoint where MITM resistance isn't critical for this use case.
_SSL_CTX: Optional[ssl.SSLContext] = None

# --------------------------------------------------------------------------
# Keyword lexicons
# --------------------------------------------------------------------------
# Deliberately short and high-precision. A hit here flips a boolean flag
# in the output; false positives are worse than false negatives because
# they surface to the user as headline evidence.

DEATH_KEYWORDS = (
    "shutdown", "shuts down", "shut down", "shutting down",
    "ceased operations", "ceasing operations",
    "defunct", "bankruptcy", "bankrupt", "goes bankrupt",
    "chapter 11", "chapter 7", "winding down", "wound down",
    "lays off", "laid off", "layoffs", "layoff",
    "fire sale", "closed its doors", "closing its doors",
)

HEALTH_KEYWORDS = (
    "raised", "raises", "series a", "series b", "series c",
    "series d", "seed round", "pre-seed", "valuation",
    "launches", "launched", "unveils", "debuts",
    "ipo", "files to go public", "goes public",
    "acquires", "acquisition of",  # note: "acquires X" = they're the buyer
    "partners with", "partnership with",
)


# --------------------------------------------------------------------------
# Source allowlist
# --------------------------------------------------------------------------
# Credible startup / business press. Headlines from these domains are
# trusted; everything else is kept as a weak signal but deprioritized
# when attributing death/health hits.
#
# Curated conservatively — prefer false negatives (missing a real story
# from an outlet we don't recognize) over false positives (attributing
# the company's fate to an SEO farm).
#
# Extend by passing --trusted-sources-file pointing at a text file of
# additional domains (one per line).

TRUSTED_SOURCES = frozenset({
    # Startup & VC press
    "techcrunch.com",
    "theinformation.com",
    "axios.com",
    "forbes.com",
    "venturebeat.com",
    "businessinsider.com",
    "crunchbasenews.com",
    "news.crunchbase.com",
    "pitchbook.com",
    "sifted.eu",
    "semafor.com",
    # Business / financial press
    "bloomberg.com",
    "reuters.com",
    "wsj.com",
    "ft.com",
    "nytimes.com",
    "washingtonpost.com",
    "economist.com",
    "cnbc.com",
    "fortune.com",
    "fastcompany.com",
    "marketwatch.com",
    # Tech press
    "theverge.com",
    "wired.com",
    "arstechnica.com",
    "theregister.com",
    "engadget.com",
    "theguardian.com",
    "theatlantic.com",
    "technologyreview.com",
    # Regulatory filings / primary sources
    "sec.gov",
    "apnews.com",
    "prnewswire.com",  # press releases — first-party but still useful
    "businesswire.com",
})


def extract_domain(url_or_host: str) -> str:
    """Return the registrable-ish domain (no scheme, no www)."""
    if not url_or_host:
        return ""
    host = url_or_host.strip().lower()
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0]
    host = host.split("?", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m."):
        host = host[2:]
    return host.rstrip(".")


def is_trusted(domain: str, extra: Optional[frozenset] = None) -> bool:
    """Allowlist membership — with optional extra user-provided domains."""
    if not domain:
        return False
    pool = TRUSTED_SOURCES if extra is None else (TRUSTED_SOURCES | extra)
    if domain in pool:
        return True
    # Accept subdomains too (e.g. "news.crunchbase.com" under "crunchbase.com")
    for trusted in pool:
        if domain.endswith("." + trusted):
            return True
    return False


# --------------------------------------------------------------------------
# HTTP + parse
# --------------------------------------------------------------------------


def build_query(name: str) -> str:
    """Quoted-name query with disambiguating startup keywords."""
    clean = name.replace('"', "").strip()
    # Disjunction of the signals we're trying to surface boosts relevance
    # without hiding less-noisy mentions.
    return (
        f'"{clean}" '
        '(shutdown OR acquired OR layoffs OR funding OR raised OR '
        '"Series A" OR "Series B" OR launches OR IPO)'
    )


def fetch_rss(query: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str]:
    """GET Google News RSS, return (xml_text, resolved_url)."""
    url = (
        f"{RSS_URL}?q={urllib.parse.quote(query)}"
        "&hl=en-US&gl=US&ceid=US:en"
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
        return resp.read().decode("utf-8", errors="ignore"), url


def parse_items(xml_text: str) -> list[dict]:
    """Extract RSS <item> entries: title, link, pub_date, source."""
    items: list[dict] = []
    if not xml_text.strip():
        return items
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_raw = (item.findtext("pubDate") or "").strip()
        src = item.find("source")
        source = (src.text or "").strip() if src is not None else ""
        source_url = (src.get("url") if src is not None else "") or ""
        source_domain = extract_domain(source_url)
        pub_dt: Optional[datetime] = None
        if pub_raw:
            try:
                pub_dt = parsedate_to_datetime(pub_raw)
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pub_dt = None
        items.append({
            "title": title,
            "link": link,
            "pub_date": pub_dt,
            "source": source,
            "source_domain": source_domain,
        })
    return items


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------


def _matches(title: str, keywords: tuple[str, ...]) -> Optional[str]:
    """Return the first keyword that matches, else None."""
    low = title.lower()
    for k in keywords:
        if k in low:
            return k
    return None


# Generic brand suffixes/prefixes — stripped before picking the distinctive
# token. Otherwise every "AI" startup matches every headline with "AI" in it.
_GENERIC_TOKENS = frozenset({
    "ai", "inc", "inc.", "co", "co.", "corp", "corp.", "labs", "lab",
    "technologies", "tech", "the", "company", "io", "app", "apps",
    "software", "systems", "solutions", "group",
})


def _distinctive_tokens(name: str) -> list[str]:
    """Pick the non-generic tokens from a company name.

    "Inflection AI" → ["inflection"]
    "Character.AI"  → ["character"]
    "Sterling Labs, Inc" → ["sterling"]
    "Abel"          → ["abel"]  (short but only option)
    """
    # Normalize punctuation → space, lowercase
    norm = re.sub(r"[^a-z0-9\s]", " ", name.lower())
    tokens = [t for t in norm.split() if t]
    distinct = [t for t in tokens if t not in _GENERIC_TOKENS and len(t) >= 3]
    if not distinct:
        # All tokens were generic or too short — fall back to the full set
        # so we at least require *something* from the name in the title.
        distinct = tokens
    return distinct


def title_about_company(title: str, name: str) -> bool:
    """Is the article title actually about this company?

    Google News returns articles whose body merely contains the query
    string; without this filter, "xAI IPO" gets attributed to "Inflection
    AI" because the article happened to mention Inflection somewhere.
    We require at least one distinctive token from the company name to
    appear as a word in the headline itself.
    """
    if not title or not name:
        return False
    distinct = _distinctive_tokens(name)
    if not distinct:
        return False
    # Word-boundary match handles possessives ("Inflection's ..."),
    # punctuation, and prevents "able" from matching "Abel".
    for tok in distinct:
        if re.search(rf"\b{re.escape(tok)}\b", title, re.IGNORECASE):
            return True
    return False


def _pick_hit(
    items: list[dict],
    keywords: tuple[str, ...],
    extra_trusted: Optional[frozenset] = None,
) -> Optional[dict]:
    """Pick the best keyword match: trusted source first, any source fallback.

    Within each tier, the most recent headline wins. This means a Bloomberg
    article from 20 days ago beats an SEO farm from 2 days ago — but an
    untrusted headline is still returned if no trusted one matched, with
    a flag so downstream code can disclose the weaker signal.
    """
    trusted_hits: list[dict] = []
    untrusted_hits: list[dict] = []
    for it in items:
        if not _matches(it["title"], keywords):
            continue
        if is_trusted(it.get("source_domain", ""), extra_trusted):
            trusted_hits.append(it)
        else:
            untrusted_hits.append(it)
    pool = trusted_hits or untrusted_hits
    if not pool:
        return None
    return max(pool, key=lambda i: i["pub_date"])


def classify(
    items: list[dict],
    now: datetime,
    name: str = "",
    extra_trusted: Optional[frozenset] = None,
    trusted_only: bool = False,
) -> dict:
    """Collapse a list of news items into per-company signal fields.

    Only items whose TITLE actually references the company are eligible
    to become death/health signals. Items that merely mention the company
    in the body are noise. If trusted_only, also require the source domain
    to be in the trusted allowlist — at the cost of potentially missing
    coverage from outlets we don't recognize.
    """
    recent = [
        i for i in items
        if i["pub_date"] and (now - i["pub_date"]).days <= WINDOW_DAYS
    ]

    if name:
        on_topic = [i for i in recent if title_about_company(i["title"], name)]
    else:
        on_topic = recent

    if trusted_only:
        eligible = [i for i in on_topic
                    if is_trusted(i.get("source_domain", ""), extra_trusted)]
    else:
        eligible = on_topic

    last_days: Optional[int] = None
    if eligible:
        newest = max(eligible, key=lambda i: i["pub_date"])
        last_days = (now - newest["pub_date"]).days

    death_hit = _pick_hit(eligible, DEATH_KEYWORDS, extra_trusted)
    health_hit = _pick_hit(eligible, HEALTH_KEYWORDS, extra_trusted)

    def _src_trust(hit: Optional[dict]) -> bool:
        return bool(hit and is_trusted(hit.get("source_domain", ""),
                                       extra_trusted))

    return {
        "news_item_count_180d": len(eligible),
        "news_item_count_raw": len(recent),  # includes off-topic mentions
        "news_last_mention_days": last_days,
        "news_death_signal": bool(death_hit),
        "news_health_signal": bool(health_hit),
        "news_death_headline": death_hit["title"] if death_hit else "",
        "news_death_link": death_hit["link"] if death_hit else "",
        "news_death_source": death_hit.get("source", "") if death_hit else "",
        "news_death_source_domain": death_hit.get("source_domain", "") if death_hit else "",
        "news_death_source_trusted": _src_trust(death_hit),
        "news_health_headline": health_hit["title"] if health_hit else "",
        "news_health_link": health_hit["link"] if health_hit else "",
        "news_health_source": health_hit.get("source", "") if health_hit else "",
        "news_health_source_domain": health_hit.get("source_domain", "") if health_hit else "",
        "news_health_source_trusted": _src_trust(health_hit),
    }


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------


def collect_one(
    name: str,
    now: datetime,
    timeout: int,
    extra_trusted: Optional[frozenset] = None,
    trusted_only: bool = False,
) -> dict:
    query = build_query(name)
    xml_text, url = fetch_rss(query, timeout=timeout)
    items = parse_items(xml_text)
    record = classify(items, now, name=name,
                      extra_trusted=extra_trusted,
                      trusted_only=trusted_only)
    record["query_url"] = url
    record["checked_at"] = now.isoformat(timespec="seconds")
    return record


def collect_all(
    input_csv: str,
    output_json: str,
    sleep: float,
    limit: Optional[int],
    timeout: int,
    extra_trusted: Optional[frozenset] = None,
    trusted_only: bool = False,
) -> int:
    with open(input_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if limit:
        rows = rows[:limit]

    # If output exists, merge on top — let repeat runs be resumable.
    existing: dict = {}
    if os.path.exists(output_json):
        try:
            with open(output_json, encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}

    now = datetime.now(timezone.utc)
    out = dict(existing)
    ssl_hinted = False
    for i, row in enumerate(rows, 1):
        name = (row.get("name") or "").strip()
        if not name:
            continue
        print(f"[{i}/{len(rows)}] {name}", file=sys.stderr)
        try:
            out[name] = collect_one(name, now, timeout,
                                    extra_trusted=extra_trusted,
                                    trusted_only=trusted_only)
        except Exception as e:  # noqa: BLE001 — log everything, continue
            out[name] = {"error": f"{type(e).__name__}: {e}"}
            print(f"  ! {e}", file=sys.stderr)
            if (not ssl_hinted) and "CERTIFICATE_VERIFY_FAILED" in str(e):
                print(
                    "    HINT: macOS Python is missing its CA bundle. "
                    "Either run\n"
                    "      /Applications/Python\\ 3.X/Install\\ "
                    "Certificates.command  (proper fix)\n"
                    "    or re-run this script with --insecure  "
                    "(Google News RSS is public).",
                    file=sys.stderr,
                )
                ssl_hinted = True
        time.sleep(sleep)

    os.makedirs(os.path.dirname(output_json) or ".", exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(out)} records to {output_json}", file=sys.stderr)

    death_count = sum(1 for v in out.values()
                      if isinstance(v, dict) and v.get("news_death_signal"))
    health_count = sum(1 for v in out.values()
                       if isinstance(v, dict) and v.get("news_health_signal"))
    death_trusted = sum(1 for v in out.values()
                        if isinstance(v, dict)
                        and v.get("news_death_source_trusted"))
    health_trusted = sum(1 for v in out.values()
                         if isinstance(v, dict)
                         and v.get("news_health_source_trusted"))
    print(f"  death signals: {death_count} (trusted: {death_trusted})  "
          f"health signals: {health_count} (trusted: {health_trusted})",
          file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="data/startups.csv",
                    help="Input CSV with a 'name' column")
    ap.add_argument("--output", default="output/news.json",
                    help="Output JSON map: name -> news signals")
    ap.add_argument("--sleep", type=float, default=1.0,
                    help="Seconds between requests (be polite)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Only process first N rows (useful for testing)")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                    help="Per-request HTTP timeout (seconds)")
    ap.add_argument("--insecure", action="store_true",
                    help="Disable SSL cert verification. Use this if you "
                         "hit CERTIFICATE_VERIFY_FAILED on macOS. Proper "
                         "fix is to run /Applications/Python\\ 3.X/Install"
                         "\\ Certificates.command once.")
    # Trusted-source enforcement is the DEFAULT. Untrusted sources never
    # get attributed as death/health evidence — they're dropped at the
    # classifier stage. Use --allow-untrusted to re-enable the old
    # soft-preference behavior (trusted first, untrusted fallback).
    ap.add_argument("--allow-untrusted", action="store_true",
                    help="Use untrusted headlines as fallback evidence when "
                         "no trusted source covered the company. Off by "
                         "default — trusted sources or no signal.")
    ap.add_argument("--trusted-sources-file", default=None,
                    help="Path to a file of additional trusted domains, "
                         "one per line. Appended to the built-in allowlist.")
    args = ap.parse_args()

    if args.insecure:
        global _SSL_CTX
        _SSL_CTX = ssl._create_unverified_context()
        print("WARNING: SSL certificate verification DISABLED (--insecure)",
              file=sys.stderr)

    extra_trusted: Optional[frozenset] = None
    if args.trusted_sources_file:
        try:
            with open(args.trusted_sources_file, encoding="utf-8") as f:
                domains = {extract_domain(line) for line in f
                           if line.strip() and not line.startswith("#")}
                extra_trusted = frozenset(d for d in domains if d)
            print(f"Added {len(extra_trusted)} extra trusted domains from "
                  f"{args.trusted_sources_file}", file=sys.stderr)
        except OSError as e:
            print(f"ERROR: cannot read {args.trusted_sources_file}: {e}",
                  file=sys.stderr)
            return 2

    return collect_all(args.input, args.output, args.sleep, args.limit,
                       args.timeout, extra_trusted=extra_trusted,
                       trusted_only=not args.allow_untrusted)


if __name__ == "__main__":
    raise SystemExit(main())
