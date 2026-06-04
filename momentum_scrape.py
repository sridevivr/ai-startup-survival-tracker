"""Step 2 — polite homepage scrape of the 144 master companies.

Reads:
    data/master.csv

Writes:
    data/scraped/<slug>.txt   — plain-text dump of the homepage
    data/scraped/_report.json — per-company status + bytes + duration

Used downstream by:
    Step 3 (funding regex over scraped text)
    Step 4 (sub-sector classification from homepage copy + tagline)

Polite at 1 request/second. Reuses the USER_AGENT convention from
tracker.py for consistency.
"""
from __future__ import annotations

import csv
import html
import json
import os
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
MASTER_CSV = os.path.join(ROOT, "data", "master.csv")
SCRAPE_DIR = os.path.join(ROOT, "data", "scraped")
REPORT_PATH = os.path.join(SCRAPE_DIR, "_report.json")

USER_AGENT = (
    "Mozilla/5.0 (compatible; AIStartupMomentumHeatmap/0.1; "
    "+https://github.com/example/ai-startup-survival-tracker)"
)
TIMEOUT = 12  # generous — some marketing sites are slow
SLEEP_SECONDS = 1.0
MAX_TEXT_BYTES = 250_000  # cap to avoid pathological pages


class TextExtractor(HTMLParser):
    """Strip tags. Skip script/style/noscript/svg blocks."""
    SKIP_TAGS = {"script", "style", "noscript", "svg", "iframe", "form"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.depth_skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self.depth_skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS:
            self.depth_skip = max(0, self.depth_skip - 1)

    def handle_data(self, data):
        if self.depth_skip:
            return
        chunk = data.strip()
        if chunk:
            self.parts.append(chunk)

    def get_text(self) -> str:
        text = "\n".join(self.parts)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower())
    return s.strip("-")[:80]


def extract_text(html_str: str) -> str:
    try:
        p = TextExtractor()
        p.feed(html_str)
        return p.get_text()
    except Exception:
        # Fallback: crude regex strip
        text = re.sub(r"<script.*?</script>", " ", html_str, flags=re.S | re.I)
        text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        return re.sub(r"\s+", " ", text).strip()


def fetch_one(sess: requests.Session, url: str) -> tuple[int | None, str | None, str | None]:
    """Return (http_status, text_content, error_message)."""
    if not url:
        return None, None, "no_url"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        r = sess.get(url, timeout=TIMEOUT, allow_redirects=True)
        body = r.text
        if len(body.encode("utf-8", errors="ignore")) > MAX_TEXT_BYTES * 4:
            body = body[: MAX_TEXT_BYTES * 4]
        text = extract_text(body)
        if len(text) > MAX_TEXT_BYTES:
            text = text[:MAX_TEXT_BYTES]
        return r.status_code, text, None
    except requests.exceptions.SSLError as e:
        return None, None, f"ssl: {e.__class__.__name__}"
    except requests.exceptions.ConnectionError as e:
        return None, None, f"conn: {e.__class__.__name__}"
    except requests.exceptions.Timeout:
        return None, None, "timeout"
    except requests.exceptions.RequestException as e:
        return None, None, f"req: {e.__class__.__name__}"
    except Exception as e:
        return None, None, f"other: {e.__class__.__name__}"


def main() -> None:
    os.makedirs(SCRAPE_DIR, exist_ok=True)

    with open(MASTER_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    sess = requests.Session()
    sess.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,*/*"})

    report: dict[str, dict] = {}
    n_ok, n_fail, n_empty = 0, 0, 0
    started = time.time()

    for i, row in enumerate(rows, 1):
        name = row["name"]
        website = row.get("website", "").strip()
        slug = slugify(name)
        status, text, err = fetch_one(sess, website)
        out_path = os.path.join(SCRAPE_DIR, f"{slug}.txt")

        ok = status is not None and 200 <= status < 400 and text
        if ok:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(text)
            n_ok += 1
            if len(text) < 200:
                n_empty += 1  # likely SPA / JS-only landing
        else:
            n_fail += 1

        report[name] = {
            "slug": slug,
            "website": website,
            "http_status": status,
            "error": err,
            "text_bytes": len(text or ""),
            "ok": bool(ok),
        }

        # Progress every 20
        if i % 20 == 0 or i == len(rows):
            elapsed = time.time() - started
            print(f"  [{i:>3}/{len(rows)}] ok={n_ok}  fail={n_fail}  empty={n_empty}  "
                  f"({elapsed:.0f}s elapsed)")

        time.sleep(SLEEP_SECONDS)

    report_meta = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "total": len(rows),
        "ok": n_ok,
        "fail": n_fail,
        "thin_text": n_empty,
        "ok_share": round(n_ok / len(rows), 3),
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump({"meta": report_meta, "per_company": report}, f, indent=2)

    print()
    print(f"Scrape complete.")
    print(f"  Wrote {n_ok}/{len(rows)} text files to {SCRAPE_DIR}/")
    print(f"  {n_fail} failures, {n_empty} thin-text (likely JS-only landing)")
    print(f"  Report at {REPORT_PATH}")


if __name__ == "__main__":
    main()
