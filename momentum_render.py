"""Build output/momentum.html from data/master.csv.

Fresh visual design — NOT inheriting from build_publish.py.

Aesthetic direction: quiet editorial. Warm off-white background, display
serif (Fraunces) for the hero, Geist for body, one confident accent
(terracotta) used sparingly. Generous whitespace. Large tiles, tabular
numerals, micro-typography for labels.

Grows step by step:
  Step 1 (current):  cohort summary + count heatmap (sector × functionality)
  Step 2 (later):    signal-strength indicators per cell
  Step 3 (later):    view toggle for funding
  Step 4 (later):    "Inside Cross-industry" mini-grid
  Step 5 (later):    insights TL;DR + featured cells
"""
from __future__ import annotations

import csv
import html
import math
import os
from collections import Counter, defaultdict
from datetime import date

ROOT = os.path.dirname(os.path.abspath(__file__))
MASTER_CSV = os.path.join(ROOT, "data", "master.csv")
OUT_HTML = os.path.join(ROOT, "output", "momentum.html")

# Canonical ordering (defined locally — no import from build_publish).
FUNCTION_ORDER = [
    "Foundation Models",
    "ML Infrastructure",
    "Data Infrastructure",
    "AI Agent",
    "Copilot / Assistant",
    "Generative Product",
    "Analytics & Decisioning",
    "Research Lab",
]
FUNCTION_SHORT = {
    "Foundation Models":       "Foundation",
    "ML Infrastructure":       "ML Infra",
    "Data Infrastructure":     "Data Infra",
    "AI Agent":                "Agent",
    "Copilot / Assistant":     "Copilot",
    "Generative Product":      "Generative",
    "Analytics & Decisioning": "Analytics",
    "Research Lab":            "Research",
}

# One accent color, used sparingly. Terracotta.
ACCENT = "#C24A2C"

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,500;9..144,600;9..144,700&family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500&display=swap');

* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: #faf7f2;
  color: #1a1612;
  font-family: 'Geist', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  font-size: 16px;
  line-height: 1.6;
  font-feature-settings: 'tnum' 1, 'cv11' 1;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.wrap { max-width: 1180px; margin: 0 auto; padding: 96px 36px 120px; }
.col  { max-width: 680px; }

/* ─── Header ────────────────────────────────────────────────────── */

.eyebrow {
  font-family: 'Geist Mono', monospace;
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #8a7e6c;
  margin: 0 0 28px;
  display: flex;
  align-items: center;
  gap: 14px;
}
.eyebrow::after {
  content: '';
  display: inline-block;
  height: 1px;
  flex: 1;
  background: #d8cfbe;
  max-width: 220px;
}

h1 {
  font-family: 'Fraunces', Georgia, serif;
  font-weight: 400;
  font-size: 68px;
  line-height: 1.02;
  letter-spacing: -0.025em;
  margin: 0 0 24px;
  font-variation-settings: 'opsz' 144, 'SOFT' 50;
  color: #1a1612;
}
h1 em {
  font-style: italic;
  font-weight: 400;
  color: """ + ACCENT + """;
  font-variation-settings: 'opsz' 144, 'SOFT' 100;
}

.lede {
  font-family: 'Fraunces', Georgia, serif;
  font-size: 22px;
  font-weight: 300;
  line-height: 1.45;
  letter-spacing: -0.005em;
  color: #4a4239;
  margin: 0 0 44px;
  max-width: 660px;
}

.meta {
  display: flex;
  gap: 36px;
  flex-wrap: wrap;
  padding: 18px 0;
  border-top: 1px solid #e5dcc8;
  border-bottom: 1px solid #e5dcc8;
  font-family: 'Geist Mono', monospace;
  font-size: 12px;
  letter-spacing: 0.04em;
  color: #6a5e4a;
  margin-bottom: 80px;
}
.meta-item { display: flex; align-items: baseline; gap: 8px; }
.meta-label { text-transform: uppercase; color: #9a8e7a; font-size: 10px; letter-spacing: 0.12em; }
.meta-value { color: #1a1612; font-weight: 500; }
.meta-value b {
  font-family: 'Fraunces', Georgia, serif;
  font-weight: 500;
  font-size: 18px;
  color: """ + ACCENT + """;
}

/* ─── Section ───────────────────────────────────────────────────── */

section { margin-bottom: 96px; }
.section-label {
  font-family: 'Geist Mono', monospace;
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #8a7e6c;
  margin: 0 0 32px;
  padding-bottom: 14px;
  border-bottom: 1px solid #e5dcc8;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.section-label .num {
  font-family: 'Fraunces', Georgia, serif;
  font-size: 13px;
  color: """ + ACCENT + """;
  font-style: italic;
}

.prose {
  font-size: 17px;
  line-height: 1.7;
  color: #2a241c;
  max-width: 660px;
  font-weight: 400;
}
.prose b { color: """ + ACCENT + """; font-weight: 500; }
.prose + .prose { margin-top: 12px; }

/* ─── Heatmap ───────────────────────────────────────────────────── */

.heatmap {
  margin: 8px -8px 0;
  overflow-x: auto;
  padding: 8px;
}
.heatmap svg {
  display: block;
  min-width: 720px;
}
.heatmap-meta {
  margin-top: 28px;
  display: flex;
  gap: 28px;
  flex-wrap: wrap;
  align-items: center;
  font-family: 'Geist Mono', monospace;
  font-size: 11px;
  letter-spacing: 0.04em;
  color: #8a7e6c;
}
.heatmap-meta .swatch-row {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.heatmap-meta .swatch {
  display: inline-block;
  width: 22px;
  height: 12px;
  border: 1px solid rgba(0,0,0,0.06);
}

/* ─── Footer ────────────────────────────────────────────────────── */

footer {
  margin-top: 80px;
  padding-top: 32px;
  border-top: 1px solid #e5dcc8;
  font-family: 'Geist Mono', monospace;
  font-size: 11px;
  letter-spacing: 0.04em;
  color: #9a8e7a;
  max-width: 680px;
}

@media (max-width: 720px) {
  .wrap { padding: 56px 22px 80px; }
  h1 { font-size: 44px; }
  .lede { font-size: 19px; }
}
"""


def load_master() -> list[dict]:
    with open(MASTER_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def density_heatmap_svg(rows: list[dict]) -> str:
    """Tile-based heatmap. One accent color, opacity grades by count.
    Empty cells nearly disappear (very faint dotted outline)."""
    matrix: dict[tuple[str, str], int] = defaultdict(int)
    sector_n: Counter[str] = Counter()
    func_n: Counter[str] = Counter()
    for r in rows:
        s = (r.get("sector") or "—").strip()
        f = (r.get("functionality") or "—").strip()
        matrix[(s, f)] += 1
        sector_n[s] += 1
        func_n[f] += 1

    sectors = [s for s, _ in sector_n.most_common() if s != "—"]
    functions = [f for f in FUNCTION_ORDER if func_n.get(f, 0) > 0]

    if not sectors or not functions:
        return "<p>No data.</p>"

    # Tile dimensions — bigger and squarer than the survival heatmap
    tile_w, tile_h = 102, 64
    gap = 4
    pad_left, pad_top = 188, 92

    cols = len(functions)
    rows_n = len(sectors)
    width = pad_left + cols * (tile_w + gap) - gap + 32
    height = pad_top + rows_n * (tile_h + gap) - gap + 24

    cell_max = max(matrix.values()) or 1

    parts: list[str] = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'preserveAspectRatio="xMinYMin meet" xmlns="http://www.w3.org/2000/svg">'
    ]

    # ─── Column headers (function names) ─────────────────────────
    for j, f in enumerate(functions):
        x = pad_left + j * (tile_w + gap) + tile_w / 2
        label = FUNCTION_SHORT.get(f, f)
        parts.append(
            f'<text x="{x}" y="{pad_top - 36}" text-anchor="middle" '
            f'font-family="Geist Mono, monospace" font-size="10" '
            f'fill="#8a7e6c" letter-spacing="0.5">'
            f'{html.escape(label.upper())}</text>'
            f'<text x="{x}" y="{pad_top - 18}" text-anchor="middle" '
            f'font-family="Fraunces, Georgia, serif" font-size="13" '
            f'font-style="italic" fill="#1a1612">{func_n[f]}</text>'
        )

    # Hairline between header and grid
    parts.append(
        f'<line x1="{pad_left - 16}" y1="{pad_top - 8}" '
        f'x2="{width - 16}" y2="{pad_top - 8}" '
        f'stroke="#e5dcc8" stroke-width="1"/>'
    )

    # ─── Rows ────────────────────────────────────────────────────
    for i, s in enumerate(sectors):
        y = pad_top + i * (tile_h + gap)
        # Sector label + N
        parts.append(
            f'<text x="{pad_left - 18}" y="{y + tile_h / 2 - 2}" '
            f'text-anchor="end" font-family="Geist, sans-serif" font-size="14" '
            f'font-weight="500" fill="#1a1612">{html.escape(s)}</text>'
            f'<text x="{pad_left - 18}" y="{y + tile_h / 2 + 14}" '
            f'text-anchor="end" font-family="Geist Mono, monospace" font-size="10" '
            f'fill="#9a8e7a">N={sector_n[s]}</text>'
        )

        for j, f in enumerate(functions):
            x = pad_left + j * (tile_w + gap)
            cnt = matrix.get((s, f), 0)
            cx = x + tile_w / 2
            cy = y + tile_h / 2

            if cnt == 0:
                # Empty cell: tiny dot only, very subtle
                parts.append(
                    f'<circle cx="{cx}" cy="{cy}" r="1.5" '
                    f'fill="#d8cfbe"/>'
                )
                continue

            # Tile fill — opacity scales by sqrt(count / max), min 0.10 so
            # 1-count cells are still readable.
            alpha = 0.10 + 0.80 * math.sqrt(cnt / cell_max)
            text_color = "#fff" if alpha >= 0.55 else "#1a1612"
            parts.append(
                f'<rect x="{x}" y="{y}" width="{tile_w}" height="{tile_h}" '
                f'rx="2" fill="{ACCENT}" fill-opacity="{alpha:.3f}">'
                f'<title>{html.escape(s)} · {html.escape(f)}: {cnt}</title></rect>'
                f'<text x="{cx}" y="{cy + 8}" text-anchor="middle" '
                f'font-family="Fraunces, Georgia, serif" font-size="26" '
                f'font-weight="500" fill="{text_color}">{cnt}</text>'
            )

    parts.append("</svg>")
    return "".join(parts)


def render(rows: list[dict]) -> str:
    n = len(rows)
    fy: Counter[str] = Counter()
    for r in rows:
        fy[r.get("founded_year", "?")] += 1

    sector_n: Counter[str] = Counter(
        (r.get("sector") or "—").strip() for r in rows
    )
    func_n: Counter[str] = Counter(
        (r.get("functionality") or "—").strip() for r in rows
    )

    top_cell_label = ""
    matrix: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        matrix[((r.get("sector") or "—"), (r.get("functionality") or "—"))] += 1
    top_cell, top_cell_n = max(matrix.items(), key=lambda kv: kv[1])
    top_cell_label = f"{top_cell[0]} × {top_cell[1]}"

    cross_n = sector_n.get("Cross-industry", 0)
    today = date.today().isoformat()
    heatmap = density_heatmap_svg(rows)

    body = f"""
<header>
  <p class="eyebrow">Report · Post-ChatGPT YC AI Cohort</p>
  <h1>Where the <em>heat</em><br>is building.</h1>
  <p class="lede">
    578 YC AI startups. We cut to {n} with at least one sign of life
    in the last six months. Now we ask: which sector × functionality
    intersections are actually heating up — by count, by activity,
    by funding, and by recency.
  </p>
  <div class="meta">
    <div class="meta-item"><span class="meta-label">Cohort</span> <span class="meta-value"><b>{n}</b> startups</span></div>
    <div class="meta-item"><span class="meta-label">Founded</span> <span class="meta-value">{html.escape(", ".join(f"{y}·{c}" for y, c in sorted(fy.items())))}</span></div>
    <div class="meta-item"><span class="meta-label">Densest cell</span> <span class="meta-value">{html.escape(top_cell_label)} · {top_cell_n}</span></div>
    <div class="meta-item"><span class="meta-label">Built</span> <span class="meta-value">{today}</span></div>
  </div>
</header>

<section class="col">
  <p class="section-label">
    <span>I · Cohort math</span><span class="num">how we got to {n}</span>
  </p>
  <p class="prose">
    We started with 578 YC AI startups. We focused on the post-ChatGPT
    founder generation — companies <b>founded in 2023 or later</b>
    (534 remain). We dropped companies marked dead, pivoted, or
    dormant (–63). Finally, we dropped companies showing
    <b>zero positive momentum signals</b> over the last 180 days (–327).
  </p>
  <p class="prose">
    A positive momentum signal is one of five: recent news, a fresh
    website (≤90 days), open job listings, recent blog posts, or
    active GitHub commits. We require at least one. {n} companies clear
    the bar.
  </p>
</section>

<section>
  <p class="section-label">
    <span>II · Density</span><span class="num">where the companies are</span>
  </p>
  <div class="heatmap">
    {heatmap}
  </div>
  <div class="heatmap-meta">
    <span class="swatch-row">
      <span class="swatch" style="background: {ACCENT}; opacity: 0.10"></span>
      <span class="swatch" style="background: {ACCENT}; opacity: 0.35"></span>
      <span class="swatch" style="background: {ACCENT}; opacity: 0.70"></span>
      <span class="swatch" style="background: {ACCENT}; opacity: 0.90"></span>
      <span>fewer ←→ more</span>
    </span>
    <span>· empty cells shown as dots</span>
    <span>· numbers are company counts</span>
  </div>
</section>

<section class="col">
  <p class="section-label">
    <span>III · What's next</span><span class="num">step 2 of 6</span>
  </p>
  <p class="prose">
    Cross-industry is still the largest row at <b>{cross_n} of {n}</b>
    — Step 4 cracks that open into sub-sectors. Step 2 next: layer
    signal-strength indicators onto each tile, so the same grid starts
    showing not just how many companies are in each cell, but how
    active they are. Step 3 adds a funding view. Step 5 surfaces
    problem themes and pulls findings up to the top of this page.
  </p>
</section>

<footer>
  YC AI Momentum Heatmap · cohort built {today} from <code>data/master.csv</code> · step 1 of 6
</footer>
"""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Where the heat is building · YC AI Momentum Heatmap</title>
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
