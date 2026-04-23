"""
Bulk-scrape company homepages for classification input.

For each row in the seed dataset, fetch the homepage in parallel and
extract a handful of narrow fields that tell us what the company does:

    - title          ← <title>
    - h1             ← first <h1>
    - meta_description ← <meta name="description">
    - og_description   ← <meta property="og:description">
    - first_paragraph  ← first <p> with substantive text under <main> / <body>
    - h2_list          ← up to 5 <h2> headings

That gives the classifier ~500 characters of homepage signal per company,
enough to pin down both Sector (Healthcare, Finance, ...) and Function
(Agent, Copilot, Infrastructure, ...) without forcing a browser session
per row.

Pipeline shape:

    python scripts/scrape_sites.py                      # all 577 rows
    python scripts/scrape_sites.py --only "Cursor,Anthropic"
    python scripts/scrape_sites.py --limit 50 --workers 30

Design decisions:

  * requests + ThreadPoolExecutor. aiohttp / httpx would be ~the same speed
    for this workload but aren't available in the sandbox; the stdlib
    concurrent-futures pattern does the job.
  * BeautifulSoup with the lxml parser when available, html.parser otherwise.
  * Conservative defaults: 10s timeout, 20 worker threads, one polite UA.
    ~1 minute for 577 rows on a cold run.
  * Failures are captured with a `status` field — the classifier treats
    those rows as "work from tagline alone" rather than dropping them.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    raise SystemExit("requests not installed. (Unexpected — it ships with most Python distributions.)")

try:
    from bs4 import BeautifulSoup
except ImportError:
    raise SystemExit("beautifulsoup4 not installed.")


USER_AGENT = (
    "Mozilla/5.0 (compatible; AIStartupSurvivalTracker-Scraper/1.0; "
    "+https://github.com/sridevivr/ai-startup-survival-tracker)"
)


@dataclass
class ScrapeResult:
    name: str
    website: str
    status: str = "ok"               # ok | http_error | timeout | connect_error | invalid_url | empty
    http_status: int | None = None
    title: str = ""
    h1: str = ""
    meta_description: str = ""
    og_description: str = ""
    first_paragraph: str = ""
    h2_list: list[str] = field(default_factory=list)
    final_url: str = ""
    note: str = ""


def _parser_name() -> str:
    try:
        import lxml  # noqa: F401
        return "lxml"
    except ImportError:
        return "html.parser"


def _clean(text: str | None, max_len: int = 400) -> str:
    """Collapse whitespace and trim length."""
    if not text:
        return ""
    t = " ".join(text.split())
    if len(t) > max_len:
        t = t[:max_len].rsplit(" ", 1)[0] + "…"
    return t


def _valid_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if "://" not in url:
        url = "https://" + url
    try:
        p = urlparse(url)
        if not p.netloc:
            return None
        return url
    except ValueError:
        return None


def _extract(html: str, website: str, final_url: str, http_status: int) -> ScrapeResult:
    soup = BeautifulSoup(html, _parser_name())
    res = ScrapeResult(name="", website=website, final_url=final_url,
                       http_status=http_status, status="ok")

    if soup.title and soup.title.string:
        res.title = _clean(soup.title.string, 200)

    h1 = soup.find("h1")
    if h1:
        res.h1 = _clean(h1.get_text(" ", strip=True), 300)

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        res.meta_description = _clean(meta_desc["content"], 400)

    og_desc = soup.find("meta", attrs={"property": "og:description"})
    if og_desc and og_desc.get("content"):
        res.og_description = _clean(og_desc["content"], 400)

    # Pick the first substantive paragraph. Skip cookie banners / footer boilerplate.
    main = soup.find("main") or soup.body or soup
    if main:
        for p in main.find_all("p"):
            text = _clean(p.get_text(" ", strip=True), 500)
            if len(text) >= 40:
                res.first_paragraph = text
                break

    if main:
        for h2 in main.find_all("h2"):
            text = _clean(h2.get_text(" ", strip=True), 120)
            if text:
                res.h2_list.append(text)
            if len(res.h2_list) >= 5:
                break

    return res


def _build_session(timeout: float) -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=1, backoff_factor=0.3,
        status_forcelist=(502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=40, pool_maxsize=40)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })
    return s


def _fetch_one(session: requests.Session, name: str, website: str, timeout: float) -> ScrapeResult:
    url = _valid_url(website)
    if not url:
        return ScrapeResult(name=name, website=website or "",
                            status="invalid_url", note="No usable URL in seed data.")
    try:
        resp = session.get(url, timeout=timeout, allow_redirects=True)
    except requests.exceptions.Timeout:
        return ScrapeResult(name=name, website=url, status="timeout",
                            note="Request exceeded timeout.")
    except requests.exceptions.SSLError as e:
        # Retry once without SSL verification for sites with broken certs.
        try:
            resp = session.get(url, timeout=timeout, allow_redirects=True, verify=False)
        except Exception as e2:
            return ScrapeResult(name=name, website=url, status="connect_error",
                                note=f"SSL error; retry failed: {str(e2)[:100]}")
    except requests.exceptions.ConnectionError as e:
        return ScrapeResult(name=name, website=url, status="connect_error",
                            note=f"ConnectionError: {str(e)[:120]}")
    except requests.exceptions.RequestException as e:
        return ScrapeResult(name=name, website=url, status="http_error",
                            note=f"{type(e).__name__}: {str(e)[:120]}")

    final_url = resp.url
    if resp.status_code >= 400:
        return ScrapeResult(name=name, website=url, status="http_error",
                            http_status=resp.status_code, final_url=final_url,
                            note=f"HTTP {resp.status_code}")
    ct = resp.headers.get("content-type", "").lower()
    if "html" not in ct and "xml" not in ct:
        return ScrapeResult(name=name, website=url, status="empty",
                            http_status=resp.status_code, final_url=final_url,
                            note=f"Non-HTML content-type: {ct[:60]}")
    text = resp.text
    if not text or len(text) < 200:
        return ScrapeResult(name=name, website=url, status="empty",
                            http_status=resp.status_code, final_url=final_url,
                            note="Empty or near-empty body.")

    result = _extract(text, website=url, final_url=final_url,
                      http_status=resp.status_code)
    result.name = name
    return result


def _scrape_all(rows: list[dict], workers: int, timeout: float) -> list[ScrapeResult]:
    session = _build_session(timeout)
    results: list[ScrapeResult] = []
    completed = 0
    total = len(rows)
    start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {
            ex.submit(_fetch_one, session, r.get("name", ""), r.get("website", ""), timeout): r
            for r in rows
        }
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            completed += 1
            if completed % 25 == 0 or completed == total:
                elapsed = time.perf_counter() - start
                rate = completed / elapsed if elapsed else 0.0
                print(f"  [{completed:>3d}/{total}] {rate:.1f} req/s", flush=True)
    return results


def _load_rows(csv_path: Path) -> list[dict]:
    with csv_path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    p = argparse.ArgumentParser(description="Bulk-scrape company homepages for classifier input.")
    p.add_argument("--csv", default="data/startups.csv")
    p.add_argument("--out", default="data/scraped_content.json")
    p.add_argument("--workers", type=int, default=20)
    p.add_argument("--timeout", type=float, default=10.0)
    p.add_argument("--limit", type=int, default=0,
                   help="Optional cap on rows (for quick tests).")
    p.add_argument("--only", default="",
                   help="Comma-separated list of company names (case-insensitive).")
    args = p.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"Missing {csv_path}")

    rows = _load_rows(csv_path)
    if args.only:
        wanted = {n.strip().lower() for n in args.only.split(",") if n.strip()}
        rows = [r for r in rows if (r.get("name") or "").strip().lower() in wanted]
    if args.limit > 0:
        rows = rows[: args.limit]

    if not rows:
        raise SystemExit("No rows selected.")

    # Suppress the urllib3 InsecureRequestWarning from our SSL fallback.
    import warnings
    import urllib3
    warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

    print(f"Scraping {len(rows)} companies, workers={args.workers}, timeout={args.timeout}s")
    start = time.perf_counter()
    results = _scrape_all(rows, args.workers, args.timeout)
    elapsed = time.perf_counter() - start

    order = {(r.get("name") or "").strip().lower(): i for i, r in enumerate(rows)}
    results.sort(key=lambda r: order.get(r.name.strip().lower(), 10**9))

    by_status: dict[str, int] = {}
    for r in results:
        by_status[r.status] = by_status.get(r.status, 0) + 1

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, indent=2, ensure_ascii=False)

    print(f"\nFinished in {elapsed:.1f}s. Wrote {args.out} ({len(results)} rows).")
    print("Status breakdown:")
    for s, n in sorted(by_status.items(), key=lambda kv: -kv[1]):
        print(f"  {s:18s} {n:>4d}")


if __name__ == "__main__":
    main()
