"""Build output/momentum.html from data/master.csv.

Grows step by step:
  Step 1 (current):  cohort summary + count heatmap (sector × functionality)
  Step 2 (later):    signal-strength indicators per cell
  Step 3 (later):    view toggle for funding
  Step 4 (later):    "Inside Cross-industry" mini-grid
  Step 5 (later):    insights TL;DR + featured cells

For now, keep it minimal — one clean editorial page that's already
openable in a browser. We'll layer in more as we go.
"""
from __future__ import annotations

import csv
import html
import math
import os
from collections import Counter, defaultdict
from datetime import date

from build_publish import (
    FUNCTION_ORDER, FUNCTION_SHORT, FUNCTION_COLORS,
    SECTOR_ORDER, SECTOR_COLORS,
)

ROOT = os.path.dirname(os.path.abspath(__file__))
MASTER_CSV = os.path.join(ROOT, "data", "master.csv")
OUT_HTML = os.path.join(ROOT, "output", "momentum.html")

CSS = """
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", system-ui, sans-serif;
  background: #fafafa;
  color: #1a1a1a;
  line-height: 1.55;
  font-size: 16px;
}
.wrap { max-width: 1040px; margin: 0 auto; padding: 56px 28px 96px; }
.col  { max-width: 720px; }
header { margin-bottom: 40px; }
h1 {
  font-size: 36px; font-weight: 700; letter-spacing: -0.02em;
  margin: 0 0 8px;
}
.subtitle { color: #5a5a5a; font-size: 17px; margin: 0 0 20px; }
.meta {
  display: flex; gap: 24px; flex-wrap: wrap;
  font-size: 13px; color: #5a5a5a;
  padding: 14px 16px; background: #fff;
  border: 1px solid #e5e5e5; border-radius: 6px;
}
.meta b { color: #1a1a1a; font-weight: 600; }
section { margin: 48px 0; }
section h2 {
  font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em;
  color: #5a5a5a; font-weight: 600; margin: 0 0 16px;
}
section p { margin: 0 0 14px; }
.heatmap-wrap {
  background: #fff;
  border: 1px solid #e5e5e5;
  border-radius: 6px;
  padding: 20px;
  overflow-x: auto;
}
.legend {
  display: flex; gap: 18px; flex-wrap: wrap; align-items: center;
  font-size: 12px; color: #5a5a5a;
  margin-top: 14px;
}
.legend .swatch {
  display: inline-block; width: 14px; height: 14px; vertical-align: middle;
  margin-right: 6px; border: 1px solid rgba(0,0,0,0.1);
}
details {
  background: #fff; border: 1px solid #e5e5e5; border-radius: 6px;
  padding: 14px 18px;
}
details summary {
  cursor: pointer; font-weight: 600; font-size: 14px;
  user-select: none;
}
details[open] summary { margin-bottom: 10px; }
details pre {
  background: #f4f4f4; padding: 10px 12px; border-radius: 4px;
  font-size: 12px; overflow-x: auto;
}
footer { margin-top: 60px; color: #9a9a9a; font-size: 12px; }
"""


def load_master() -> list[dict]:
    with open(MASTER_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cohort_summary(rows: list[dict]) -> tuple[int, Counter[str], Counter[str]]:
    fy: Counter[str] = Counter()
    for r in rows:
        fy[r.get("founded_year", "?")] += 1
    return len(rows), fy, Counter()


def density_heatmap_svg(rows: list[dict]) -> str:
    matrix: dict[tuple[str, str], int] = defaultdict(int)
    sector_n: Counter[str] = Counter()
    func_n: Counter[str] = Counter()
    for r in rows:
        s = (r.get("sector") or "—").strip()
        f = (r.get("functionality") or "—").strip()
        matrix[(s, f)] += 1
        sector_n[s] += 1
        func_n[f] += 1

    # Order: sectors descending by total (Cross-industry naturally first),
    # functions in canonical FUNCTION_ORDER for readability.
    sectors = [s for s, _ in sector_n.most_common() if s != "—"]
    functions = [f for f in FUNCTION_ORDER if func_n.get(f, 0) > 0]

    if not sectors or not functions:
        return "<p>No data.</p>"

    row_h, col_w = 36, 116
    pad_left, pad_top = 168, 70
    width = pad_left + col_w * len(functions) + 24
    height = pad_top + row_h * len(sectors) + 50

    cell_max = max(matrix.values()) or 1

    parts: list[str] = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'preserveAspectRatio="xMinYMin meet" xmlns="http://www.w3.org/2000/svg" '
        f'font-family="-apple-system, BlinkMacSystemFont, Inter, system-ui, sans-serif">'
    ]

    # Column headers (function names)
    for j, f in enumerate(functions):
        x = pad_left + j * col_w + (col_w - 6) / 2
        label = FUNCTION_SHORT.get(f, f)
        parts.append(
            f'<text x="{x}" y="{pad_top - 16}" text-anchor="middle" '
            f'font-size="12" fill="#1a1a1a" font-weight="600">{html.escape(label)}</text>'
            f'<text x="{x}" y="{pad_top - 3}" text-anchor="middle" '
            f'font-size="10" fill="#9a9a9a">({func_n[f]})</text>'
        )

    # Rows (sector labels + cells)
    for i, s in enumerate(sectors):
        y = pad_top + i * row_h
        parts.append(
            f'<text x="{pad_left - 12}" y="{y + row_h / 2 + 4}" text-anchor="end" '
            f'font-size="12" fill="#1a1a1a" font-weight="500">{html.escape(s)} '
            f'<tspan fill="#9a9a9a" font-weight="400">({sector_n[s]})</tspan></text>'
        )
        for j, f in enumerate(functions):
            x = pad_left + j * col_w
            cnt = matrix.get((s, f), 0)
            if cnt == 0:
                parts.append(
                    f'<rect x="{x}" y="{y + 3}" width="{col_w - 6}" '
                    f'height="{row_h - 6}" fill="#f5f5f5" stroke="#e5e5e5"/>'
                )
                continue
            alpha = 0.20 + 0.78 * math.sqrt(cnt / cell_max)
            color = FUNCTION_COLORS.get(f, "#666")
            text_color = "#fff" if alpha >= 0.55 else "#1a1a1a"
            parts.append(
                f'<rect x="{x}" y="{y + 3}" width="{col_w - 6}" '
                f'height="{row_h - 6}" fill="{color}" fill-opacity="{alpha:.2f}" '
                f'stroke="{color}" stroke-opacity="0.5">'
                f'<title>{html.escape(s)} · {html.escape(f)}: {cnt}</title></rect>'
                f'<text x="{x + (col_w - 6) / 2}" y="{y + row_h / 2 + 4}" '
                f'text-anchor="middle" font-size="13" font-weight="600" '
                f'fill="{text_color}">{cnt}</text>'
            )

    parts.append("</svg>")
    return "".join(parts)


def render(rows: list[dict]) -> str:
    n, fy, _ = cohort_summary(rows)
    fy_str = ", ".join(f"{y}: {c}" for y, c in sorted(fy.items()))
    heatmap = density_heatmap_svg(rows)
    today = date.today().isoformat()

    body = f"""
<header class="col">
  <h1>YC AI Momentum Heatmap</h1>
  <p class="subtitle">
    Where is heat building across the post-ChatGPT YC AI cohort?
    Step 1 of 6 — cohort cut + density view.
  </p>
  <div class="meta">
    <span><b>{n}</b> companies</span>
    <span><b>Founded</b> {html.escape(fy_str)}</span>
    <span><b>Built</b> {today}</span>
  </div>
</header>

<section class="col">
  <h2>How we got to {n}</h2>
  <p>
    We started with 578 YC AI startups. We narrowed to companies founded in
    2023 or later (534) to focus on the post-ChatGPT founder generation. We
    cut companies marked dead, pivoted, or dormant (–63). We then cut
    companies showing zero positive momentum signals over the last 180 days
    (–327). That leaves {n} companies with at least one sign of life:
    recent news, a fresh website, active hiring, recent blog posts, or
    active GitHub commits.
  </p>
</section>

<section>
  <h2>Density — how many companies in each (sector × functionality) cell</h2>
  <div class="heatmap-wrap">
    {heatmap}
  </div>
  <div class="legend">
    <span><span class="swatch" style="background:#f5f5f5;border-color:#e5e5e5"></span>no companies in this cell</span>
    <span>color = functionality; opacity = count relative to the densest cell</span>
  </div>
</section>

<section class="col">
  <h2>What's coming next</h2>
  <p>
    Step 2 layers signal-strength indicators onto each cell. Step 3 adds a
    funding view. Step 4 cracks open Cross-industry (still the largest row
    at {sum(1 for r in rows if (r.get("sector") or "").strip() == "Cross-industry")}
    of {n}) into more meaningful sub-sectors. Step 5 surfaces problem themes
    per featured cell and pulls findings up to the top of this page.
  </p>
</section>

<footer class="col">
  <p>YC AI Momentum Heatmap · cohort built {today} from
  <code>data/master.csv</code></p>
</footer>
"""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>YC AI Momentum Heatmap</title>
<style>{CSS}</style>
</head>
<body>
<main class="wrap">
{body}
</main>
</body>
</html>"""


def main() -> None:
    rows = load_master()
    html_doc = render(rows)
    os.makedirs(os.path.dirname(OUT_HTML), exist_ok=True)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_doc)
    print(f"Wrote {len(html_doc):,} bytes to {OUT_HTML}")
    print(f"Open: file://{OUT_HTML}")


if __name__ == "__main__":
    main()
