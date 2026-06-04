"""Build output/momentum.html from data/master.csv.

Magazine-spread aesthetic. Opens with a vocabulary primer (the eight
functions of AI, with icons) before showing data.

Grows step by step:
  Step 1 (done):   vocabulary primer + cohort math + density heatmap
  Step 2 (current): activity score per company → toggle Density / Activity
                    in the same heatmap. Section IV now contrasts the two
                    views.
  Step 3 (later):   view toggle for funding
  Step 4 (later):   "Inside Cross-industry" mini-grid
  Step 5 (later):   insights TL;DR + featured cells
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
FUNCTION_DESCRIPTIONS = {
    "Foundation Models":
        "Companies training the underlying models themselves — GPT-style transformers, multimodal models, specialized LLMs. Few players. Capital-intensive.",
    "ML Infrastructure":
        "Tooling that makes training, fine-tuning, deploying, and orchestrating models possible. Pipelines, evals, GPU orchestration. Sells to ML teams.",
    "Data Infrastructure":
        "Data plumbing for AI — synthetic data, labeling, training sets, RAG pipelines, vector stores. Sells across ML and product alike.",
    "AI Agent":
        "Autonomous or semi-autonomous systems that take actions on a user's behalf. Books meetings, files tickets, runs audits. The headline post-ChatGPT category.",
    "Copilot / Assistant":
        "Embedded helpers that augment a human workflow rather than replace it. Suggests, drafts, reviews. Always in-the-loop.",
    "Generative Product":
        "End-user products where the AI output IS the product — images, video, decks, code scaffolds. Consumer- or creator-shaped.",
    "Analytics & Decisioning":
        "AI applied to reasoning over data — search, summarization, scoring, recommendations. Sells to business users who need answers, not artifacts.",
    "Research Lab":
        "Companies positioning as research orgs first, products second. Long-horizon, paper-publishing, often a talent vehicle.",
}


def _icon(svg_body: str) -> str:
    return (
        '<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" '
        'stroke-width="1.5" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true">{svg_body}</svg>'
    )


FUNCTION_ICONS = {
    "Foundation Models": _icon(
        '<rect x="6" y="26" width="28" height="8" rx="0.5"/>'
        '<rect x="10" y="17" width="20" height="8" rx="0.5"/>'
        '<rect x="14" y="8" width="12" height="8" rx="0.5"/>'
    ),
    "ML Infrastructure": _icon(
        '<circle cx="10" cy="10" r="2.6"/>'
        '<circle cx="30" cy="10" r="2.6"/>'
        '<circle cx="20" cy="20" r="2.6"/>'
        '<circle cx="10" cy="30" r="2.6"/>'
        '<circle cx="30" cy="30" r="2.6"/>'
        '<line x1="12" y1="12" x2="18" y2="18"/>'
        '<line x1="28" y1="12" x2="22" y2="18"/>'
        '<line x1="18" y1="22" x2="12" y2="28"/>'
        '<line x1="22" y1="22" x2="28" y2="28"/>'
    ),
    "Data Infrastructure": _icon(
        '<ellipse cx="20" cy="9" rx="12" ry="3"/>'
        '<path d="M 8 9 L 8 31 C 8 33 13 34 20 34 C 27 34 32 33 32 31 L 32 9"/>'
        '<path d="M 8 17 C 8 19 13 20 20 20 C 27 20 32 19 32 17"/>'
        '<path d="M 8 24 C 8 26 13 27 20 27 C 27 27 32 26 32 24"/>'
    ),
    "AI Agent": _icon(
        '<circle cx="20" cy="20" r="5"/>'
        '<path d="M 20 6 L 20 9 M 20 31 L 20 34 M 6 20 L 9 20 M 31 20 L 34 20"/>'
        '<path d="M 10 10 L 12.5 12.5 M 28 10 L 25.5 12.5 M 10 30 L 12.5 27.5 M 28 30 L 25.5 27.5"/>'
    ),
    "Copilot / Assistant": _icon(
        '<path d="M 8 10 L 32 10 C 33.5 10 34 10.5 34 12 L 34 24 C 34 25.5 33.5 26 32 26 L 19 26 L 13 31 L 13 26 L 8 26 C 6.5 26 6 25.5 6 24 L 6 12 C 6 10.5 6.5 10 8 10 Z"/>'
        '<circle cx="14" cy="18" r="1.2" fill="currentColor"/>'
        '<circle cx="20" cy="18" r="1.2" fill="currentColor"/>'
        '<circle cx="26" cy="18" r="1.2" fill="currentColor"/>'
    ),
    "Generative Product": _icon(
        '<path d="M 20 6 L 21.6 17.6 L 34 20 L 21.6 22.4 L 20 34 L 18.4 22.4 L 6 20 L 18.4 17.6 Z"/>'
        '<circle cx="20" cy="20" r="1.4"/>'
    ),
    "Analytics & Decisioning": _icon(
        '<line x1="6" y1="34" x2="34" y2="34"/>'
        '<rect x="10" y="22" width="5" height="11" rx="0.5"/>'
        '<rect x="17.5" y="14" width="5" height="19" rx="0.5"/>'
        '<rect x="25" y="8" width="5" height="25" rx="0.5"/>'
    ),
    "Research Lab": _icon(
        '<line x1="14" y1="6" x2="14" y2="16"/>'
        '<line x1="26" y1="6" x2="26" y2="16"/>'
        '<line x1="12" y1="6" x2="28" y2="6"/>'
        '<path d="M 14 16 L 7 31 C 6 33.5 7.5 35 10 35 L 30 35 C 32.5 35 34 33.5 33 31 L 26 16"/>'
        '<line x1="11" y1="26" x2="29" y2="26"/>'
    ),
}

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
  font-feature-settings: 'tnum' 1, 'ss01' 1, 'cv11' 1;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
.wrap { max-width: 1180px; margin: 0 auto; padding: 64px 36px 96px; }

/* ─── Masthead ──────────────────────────────────────────────────── */
.masthead {
  display: flex; justify-content: space-between; align-items: baseline;
  font-family: 'Geist Mono', monospace;
  font-size: 11px; letter-spacing: 0.16em; text-transform: uppercase;
  color: #8a7e6c;
  padding-bottom: 18px;
  border-bottom: 1px solid #1a1612;
  margin-bottom: 56px;
}
.masthead .title { color: #1a1612; font-weight: 500; }

/* ─── Hero ──────────────────────────────────────────────────────── */
.hero {
  display: grid;
  grid-template-columns: minmax(0, 8fr) minmax(0, 4fr);
  gap: 56px;
  margin-bottom: 96px;
  padding-bottom: 64px;
  border-bottom: 1px solid #d8cfbe;
}
.hero h1 {
  font-family: 'Fraunces', Georgia, serif;
  font-weight: 400;
  font-size: 96px; line-height: 0.95;
  letter-spacing: -0.035em;
  margin: 0 0 36px;
  font-variation-settings: 'opsz' 144, 'SOFT' 30;
  color: #1a1612;
}
.hero h1 em {
  font-style: italic; font-weight: 400;
  color: """ + ACCENT + """;
  font-variation-settings: 'opsz' 144, 'SOFT' 100;
}
.hero .lede {
  font-family: 'Fraunces', Georgia, serif;
  font-weight: 300;
  font-size: 22px; line-height: 1.5;
  color: #2a241c;
  max-width: 580px;
  margin: 0;
}
.hero .lede::first-letter {
  font-family: 'Fraunces', Georgia, serif;
  font-weight: 500;
  font-size: 64px; line-height: 0.85;
  float: left;
  padding: 6px 12px 0 0;
  color: """ + ACCENT + """;
  font-variation-settings: 'opsz' 144, 'SOFT' 100;
}

.glance { border-left: 1px solid #d8cfbe; padding-left: 32px; }
.glance-title {
  font-family: 'Geist Mono', monospace;
  font-size: 10px; letter-spacing: 0.18em; text-transform: uppercase;
  color: #8a7e6c; margin: 0 0 22px;
}
.glance-row {
  display: flex; justify-content: space-between; align-items: baseline;
  padding: 14px 0;
  border-bottom: 1px dotted #d8cfbe;
  gap: 12px;
}
.glance-row:last-child { border-bottom: none; }
.glance-key {
  font-family: 'Geist Mono', monospace;
  font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase;
  color: #8a7e6c; flex-shrink: 0;
}
.glance-val {
  font-family: 'Fraunces', Georgia, serif;
  font-size: 19px; line-height: 1.1; font-weight: 500;
  color: #1a1612; text-align: right;
  font-variation-settings: 'opsz' 36;
}
.glance-val .accent { color: """ + ACCENT + """; }
.glance-val small {
  display: block;
  font-family: 'Geist Mono', monospace;
  font-size: 10px; font-weight: 400; letter-spacing: 0.06em;
  color: #8a7e6c; margin-top: 4px;
}

/* ─── Sections ──────────────────────────────────────────────────── */
section { margin-bottom: 88px; }
.section-head {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 4fr);
  align-items: baseline;
  gap: 32px;
  padding-bottom: 16px;
  border-bottom: 1px solid #1a1612;
  margin-bottom: 36px;
}
.section-num {
  font-family: 'Fraunces', Georgia, serif;
  font-style: italic; font-weight: 400;
  font-size: 34px;
  color: """ + ACCENT + """;
  font-variation-settings: 'opsz' 144;
  line-height: 1;
}
.section-num .roman {
  font-family: 'Geist Mono', monospace;
  font-style: normal; font-size: 11px;
  letter-spacing: 0.16em; text-transform: uppercase;
  color: #8a7e6c; margin-right: 14px; vertical-align: middle;
}
.section-sub {
  font-family: 'Geist Mono', monospace;
  font-size: 11px; letter-spacing: 0.16em; text-transform: uppercase;
  color: #8a7e6c; text-align: right;
}

/* ─── Vocabulary cards ──────────────────────────────────────────── */
.vocab {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  border-top: 1px solid #d8cfbe; border-left: 1px solid #d8cfbe;
}
.vocab-card {
  padding: 28px 22px;
  border-right: 1px solid #d8cfbe; border-bottom: 1px solid #d8cfbe;
  display: flex; flex-direction: column;
  background: #fcfaf5;
}
.vocab-icon { color: """ + ACCENT + """; width: 36px; height: 36px; margin-bottom: 18px; }
.vocab-icon svg { width: 100%; height: 100%; display: block; }
.vocab-title {
  font-family: 'Geist', sans-serif; font-size: 11px;
  letter-spacing: 0.12em; text-transform: uppercase;
  font-weight: 600; color: #1a1612; margin: 0 0 4px;
}
.vocab-count {
  font-family: 'Fraunces', Georgia, serif;
  font-size: 13px; font-style: italic;
  color: #8a7e6c; margin-bottom: 14px;
  font-variation-settings: 'opsz' 36;
}
.vocab-count b { color: """ + ACCENT + """; font-style: normal; font-weight: 500; }
.vocab-desc { font-size: 13.5px; line-height: 1.55; color: #3a3128; margin: 0; }

/* ─── Cohort math (two-column body) ─────────────────────────────── */
.math-body {
  font-size: 16px; line-height: 1.7; color: #2a241c;
  column-count: 2; column-gap: 48px;
  column-rule: 1px solid #d8cfbe;
}
.math-body p { margin: 0 0 14px; break-inside: avoid; }
.math-body p:first-child::first-letter {
  font-family: 'Fraunces', Georgia, serif; font-weight: 500;
  font-size: 56px; line-height: 0.85;
  float: left; padding: 4px 10px 0 0;
  color: """ + ACCENT + """;
  font-variation-settings: 'opsz' 144, 'SOFT' 100;
}
.math-body b { color: """ + ACCENT + """; font-weight: 500; }

/* ─── View toggle (Step 2) ─────────────────────────────────────── */
.view-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0;
  margin-bottom: 28px;
  padding: 5px;
  background: #fcfaf5;
  border: 1px solid #d8cfbe;
  border-radius: 999px;
}
.view-chip {
  font-family: 'Geist Mono', monospace;
  font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase;
  color: #8a7e6c; font-weight: 500;
  padding: 9px 18px;
  background: transparent;
  border: none;
  cursor: pointer;
  border-radius: 999px;
  transition: all 0.18s ease;
}
.view-chip[aria-pressed="true"] {
  background: #1a1612;
  color: #faf7f2;
}
.view-chip[disabled] { opacity: 0.35; cursor: not-allowed; }
.view-chip:hover:not([disabled]):not([aria-pressed="true"]) { color: """ + ACCENT + """; }

.view-explain {
  font-family: 'Fraunces', Georgia, serif;
  font-style: italic; font-weight: 300;
  font-size: 17px;
  color: #3a3128;
  margin: 0 0 24px;
  max-width: 720px;
}
.view-explain b { font-style: normal; font-weight: 500; color: """ + ACCENT + """; }

/* ─── Heatmap ───────────────────────────────────────────────────── */
.heatmap { margin: 8px 0 0; overflow-x: auto; padding: 4px 0; }
.heatmap.hidden { display: none; }
.heatmap svg { display: block; min-width: 720px; }
.heatmap-caption {
  margin-top: 24px; padding-top: 16px;
  border-top: 1px dotted #d8cfbe;
  display: flex; gap: 28px; flex-wrap: wrap; align-items: center;
  font-family: 'Geist Mono', monospace;
  font-size: 11px; letter-spacing: 0.04em;
  color: #8a7e6c;
}
.swatch {
  display: inline-block; width: 22px; height: 12px;
  border: 1px solid rgba(0,0,0,0.06);
  vertical-align: middle;
}
.swatch-row { display: inline-flex; align-items: center; gap: 4px; }

/* ─── Pull quote ────────────────────────────────────────────────── */
.pullquote {
  margin: 40px 0;
  padding-left: 28px;
  border-left: 3px solid """ + ACCENT + """;
  font-family: 'Fraunces', Georgia, serif;
  font-style: italic; font-weight: 300;
  font-size: 22px; line-height: 1.4;
  color: #2a241c;
  max-width: 660px;
}

/* ─── Footer ────────────────────────────────────────────────────── */
footer {
  margin-top: 80px; padding-top: 24px;
  border-top: 1px solid #1a1612;
  font-family: 'Geist Mono', monospace;
  font-size: 11px; letter-spacing: 0.04em;
  color: #8a7e6c;
  display: flex; justify-content: space-between;
}

/* ─── Responsive ────────────────────────────────────────────────── */
@media (max-width: 880px) {
  .hero { grid-template-columns: 1fr; gap: 36px; }
  .glance { border-left: none; border-top: 1px solid #d8cfbe; padding: 28px 0 0; }
  .hero h1 { font-size: 56px; }
  .vocab { grid-template-columns: repeat(2, 1fr); }
  .math-body { column-count: 1; }
  .section-head { grid-template-columns: 1fr; }
  .section-sub { text-align: left; }
}
"""


def load_master() -> list[dict]:
    with open(MASTER_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cell_aggregates(rows: list[dict]) -> tuple[dict, dict, dict, dict]:
    """Return (count_per_cell, mean_activity_per_cell, sector_n, func_n)."""
    by_cell: dict[tuple[str, str], list[float]] = defaultdict(list)
    sector_n: Counter[str] = Counter()
    func_n: Counter[str] = Counter()
    for r in rows:
        s = (r.get("sector") or "—").strip()
        f = (r.get("functionality") or "—").strip()
        score = float(r.get("activity_score") or 0)
        by_cell[(s, f)].append(score)
        sector_n[s] += 1
        func_n[f] += 1
    count = {k: len(v) for k, v in by_cell.items()}
    mean_act = {k: round(sum(v) / len(v), 1) for k, v in by_cell.items()}
    return count, mean_act, dict(sector_n), dict(func_n)


def heatmap_svg(
    *, view_id: str, value_map: dict, count_map: dict,
    sector_n: dict, func_n: dict,
    max_value: float,
    cell_label_fn,
    low_n_dim: bool = False,
) -> str:
    """Render a heatmap SVG.

    view_id:        unique id for the <svg> (e.g. "hm-density-svg")
    value_map:      (sector, function) → numeric value driving opacity
    count_map:      (sector, function) → company count (for tooltip / N label)
    cell_label_fn:  (value, count) → string to show inside the tile
    low_n_dim:      if True, dim cells where count < 3 (for activity view)
    """
    sectors = [s for s, n in sorted(sector_n.items(), key=lambda kv: -kv[1])]
    functions = [f for f in FUNCTION_ORDER if func_n.get(f, 0) > 0]
    if not sectors or not functions:
        return "<p>No data.</p>"

    tile_w, tile_h = 102, 64
    gap = 4
    pad_left, pad_top = 188, 88

    cols, rows_n = len(functions), len(sectors)
    width = pad_left + cols * (tile_w + gap) - gap + 24
    height = pad_top + rows_n * (tile_h + gap) - gap + 16

    parts: list[str] = [
        f'<svg id="{view_id}" viewBox="0 0 {width} {height}" width="100%" '
        f'preserveAspectRatio="xMinYMin meet" xmlns="http://www.w3.org/2000/svg">'
    ]

    # Column headers
    for j, f in enumerate(functions):
        x = pad_left + j * (tile_w + gap) + tile_w / 2
        label = FUNCTION_SHORT.get(f, f)
        parts.append(
            f'<text x="{x}" y="{pad_top - 36}" text-anchor="middle" '
            f'font-family="Geist Mono, monospace" font-size="10" '
            f'fill="#8a7e6c" letter-spacing="0.5">'
            f'{html.escape(label.upper())}</text>'
            f'<text x="{x}" y="{pad_top - 18}" text-anchor="middle" '
            f'font-family="Fraunces, Georgia, serif" font-size="14" '
            f'font-style="italic" fill="#1a1612">{func_n[f]}</text>'
        )

    parts.append(
        f'<line x1="{pad_left - 16}" y1="{pad_top - 8}" '
        f'x2="{width - 12}" y2="{pad_top - 8}" '
        f'stroke="#1a1612" stroke-width="1"/>'
    )

    for i, s in enumerate(sectors):
        y = pad_top + i * (tile_h + gap)
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
            cx = x + tile_w / 2
            cy = y + tile_h / 2

            n = count_map.get((s, f), 0)
            val = value_map.get((s, f), 0)

            if n == 0:
                parts.append(f'<circle cx="{cx}" cy="{cy}" r="1.5" fill="#d8cfbe"/>')
                continue

            alpha = 0.10 + 0.80 * math.sqrt(max(0, val) / max_value) if max_value else 0.10
            if low_n_dim and n < 3:
                alpha *= 0.5  # de-emphasize 1-2-company cells in activity view
            text_color = "#fff" if alpha >= 0.55 else "#1a1612"

            label = cell_label_fn(val, n)
            stroke = f"{ACCENT}" if not (low_n_dim and n < 3) else "#a0958a"
            dash = ' stroke-dasharray="2 2"' if (low_n_dim and n < 3) else ''
            parts.append(
                f'<rect x="{x}" y="{y}" width="{tile_w}" height="{tile_h}" '
                f'rx="2" fill="{ACCENT}" fill-opacity="{alpha:.3f}" '
                f'stroke="{stroke}" stroke-opacity="0.25" stroke-width="1"{dash}>'
                f'<title>{html.escape(s)} · {html.escape(f)}: N={n}, value={val}</title></rect>'
                f'<text x="{cx}" y="{cy + 8}" text-anchor="middle" '
                f'font-family="Fraunces, Georgia, serif" font-size="26" '
                f'font-weight="500" fill="{text_color}">{label}</text>'
            )

    parts.append("</svg>")
    return "".join(parts)


JS = """
(function() {
  function setView(view) {
    document.querySelectorAll('.heatmap').forEach(function(h) {
      h.classList.toggle('hidden', h.dataset.view !== view);
    });
    document.querySelectorAll('.view-chip').forEach(function(c) {
      c.setAttribute('aria-pressed', String(c.dataset.view === view));
    });
    document.querySelectorAll('.view-explain').forEach(function(e) {
      e.style.display = (e.dataset.view === view) ? 'block' : 'none';
    });
    document.querySelectorAll('.view-caption').forEach(function(e) {
      e.style.display = (e.dataset.view === view) ? 'flex' : 'none';
    });
  }
  document.querySelectorAll('.view-chip').forEach(function(c) {
    c.addEventListener('click', function() { setView(c.dataset.view); });
  });
})();
"""


def render(rows: list[dict]) -> str:
    n = len(rows)
    fy: Counter[str] = Counter()
    for r in rows:
        fy[r.get("founded_year", "?")] += 1

    count_map, activity_map, sector_n, func_n = cell_aggregates(rows)
    sector_n_counter = Counter(sector_n)

    # For headline meta
    top_cell, top_cell_n = max(count_map.items(), key=lambda kv: kv[1])
    top_act_cell, top_act_val = max(
        ((k, v) for k, v in activity_map.items() if count_map[k] >= 3),
        key=lambda kv: kv[1],
    )
    cross_n = sector_n.get("Cross-industry", 0)
    today = date.today().isoformat()
    fy_str = ", ".join(f"{y}·{c}" for y, c in sorted(fy.items()))

    # Heatmaps
    density_svg = heatmap_svg(
        view_id="hm-density-svg",
        value_map=count_map, count_map=count_map,
        sector_n=sector_n, func_n=func_n,
        max_value=max(count_map.values()),
        cell_label_fn=lambda v, n: str(int(v)),
        low_n_dim=False,
    )
    activity_svg = heatmap_svg(
        view_id="hm-activity-svg",
        value_map=activity_map, count_map=count_map,
        sector_n=sector_n, func_n=func_n,
        max_value=100.0,
        cell_label_fn=lambda v, n: str(int(round(v))),
        low_n_dim=True,
    )

    # Vocabulary cards
    vocab_cards: list[str] = []
    for f in FUNCTION_ORDER:
        n_f = func_n.get(f, 0)
        share = (n_f / n * 100) if n else 0
        vocab_cards.append(
            f'<article class="vocab-card">'
            f'  <div class="vocab-icon">{FUNCTION_ICONS[f]}</div>'
            f'  <h3 class="vocab-title">{html.escape(f)}</h3>'
            f'  <p class="vocab-count">In cohort: <b>{n_f}</b> · {share:.0f}%</p>'
            f'  <p class="vocab-desc">{html.escape(FUNCTION_DESCRIPTIONS[f])}</p>'
            f'</article>'
        )
    vocab_html = "\n".join(vocab_cards)

    body = f"""
<div class="masthead">
  <span class="title">YC AI Momentum Heatmap</span>
  <span>Issue 01 · {today} · Step 2 of 6</span>
</div>

<header class="hero">
  <div>
    <h1>Where the<br><em>heat</em> is<br>building.</h1>
    <p class="lede">
      578 YC AI startups. We cut to {n} with at least one sign of life
      in the last six months. Then we ask the question that matters:
      which sector × functionality intersections are actually heating
      up — by count, by activity, by funding, and by recency.
    </p>
  </div>
  <aside class="glance">
    <p class="glance-title">At a glance</p>
    <div class="glance-row"><span class="glance-key">Cohort</span>
      <span class="glance-val"><span class="accent">{n}</span><small>after the cut</small></span></div>
    <div class="glance-row"><span class="glance-key">Founded</span>
      <span class="glance-val">2023–25<small>{html.escape(fy_str)}</small></span></div>
    <div class="glance-row"><span class="glance-key">Densest cell</span>
      <span class="glance-val">{html.escape(top_cell[0])}<small>× {html.escape(top_cell[1])} · {top_cell_n}</small></span></div>
    <div class="glance-row"><span class="glance-key">Hottest cell</span>
      <span class="glance-val">{html.escape(top_act_cell[0])}<small>× {html.escape(top_act_cell[1])} · avg act. {top_act_val:.0f}</small></span></div>
    <div class="glance-row"><span class="glance-key">Cross-industry</span>
      <span class="glance-val">{cross_n}<small>of {n} ({cross_n / n * 100:.0f}%)</small></span></div>
  </aside>
</header>

<section>
  <div class="section-head">
    <h2 class="section-num"><span class="roman">II</span>The vocabulary.</h2>
    <p class="section-sub">The eight functions of AI · before the data</p>
  </div>
  <p class="pullquote">
    Before we ask <em>where</em> the heat is, we have to be clear about
    <em>what</em> we're measuring. These are the eight functions every
    company in the cohort fits into.
  </p>
  <div class="vocab">
    {vocab_html}
  </div>
</section>

<section>
  <div class="section-head">
    <h2 class="section-num"><span class="roman">III</span>Cohort math.</h2>
    <p class="section-sub">How we got to {n}</p>
  </div>
  <div class="math-body">
    <p>We started with 578 YC AI startups in our dataset. To focus on the
    post-ChatGPT founder generation, we filtered to companies <b>founded
    in 2023 or later</b>. That dropped 44 pre-ChatGPT-era plays — the
    OpenAI / Anthropic / Cohere tier — and left us with 534.</p>
    <p>Next we cut companies marked as <b>dead, pivoted, or
    dormant</b> in our existing signal data. That removed 63 known
    failures and acqui-hires. 471 remained.</p>
    <p>Finally, we cut companies showing <b>zero positive momentum
    signals</b> over the last 180 days. Positive momentum is defined as
    at least one of: recent press coverage, a fresh website (≤90 days),
    open job listings, recent blog posts, or active GitHub commits. Of
    the 471, only {n} cleared that bar. The other 327 are silent.</p>
    <p>Silent does not always mean dead — many are heads-down building
    — but for a <i>momentum</i> story they're noise. We're left with
    {n} companies actually doing something we can see.</p>
  </div>
</section>

<section>
  <div class="section-head">
    <h2 class="section-num"><span class="roman">IV</span>The heatmap.</h2>
    <p class="section-sub">Density vs activity · two views, same grid</p>
  </div>

  <div class="view-toggle" role="tablist" aria-label="Heatmap view">
    <button class="view-chip" data-view="density" aria-pressed="true">Density</button>
    <button class="view-chip" data-view="activity" aria-pressed="false">Activity</button>
    <button class="view-chip" data-view="funding" aria-pressed="false" disabled title="Step 3">Funding</button>
    <button class="view-chip" data-view="recency" aria-pressed="false" disabled title="Step 5">Recency</button>
  </div>

  <p class="view-explain" data-view="density" style="display:block">
    <b>Density</b> — how many companies sit in each (sector × functionality) cell.
    Color saturation grows with count. The largest cell is
    {html.escape(top_cell[0])} × {html.escape(top_cell[1])} at {top_cell_n}.
  </p>
  <p class="view-explain" data-view="activity" style="display:none">
    <b>Activity</b> — average <i>momentum score</i> of the companies in each cell,
    on a 0–100 scale. Driven by recent press, hiring, fresh website, blog cadence,
    and GitHub commits. Cells with fewer than 3 companies are <i>dashed and dimmed</i>
    because a single outlier can dominate. Hottest by activity:
    {html.escape(top_act_cell[0])} × {html.escape(top_act_cell[1])} at {top_act_val:.0f}.
  </p>

  <div class="heatmap" data-view="density">
    {density_svg}
  </div>
  <div class="heatmap hidden" data-view="activity">
    {activity_svg}
  </div>

  <div class="view-caption heatmap-caption" data-view="density" style="display:flex">
    <span class="swatch-row">
      <span class="swatch" style="background:{ACCENT};opacity:0.10"></span>
      <span class="swatch" style="background:{ACCENT};opacity:0.35"></span>
      <span class="swatch" style="background:{ACCENT};opacity:0.70"></span>
      <span class="swatch" style="background:{ACCENT};opacity:0.95"></span>
      <span>fewer ←→ more</span>
    </span>
    <span>· empty cells: dots</span>
    <span>· numbers: company counts</span>
  </div>
  <div class="view-caption heatmap-caption" data-view="activity" style="display:none">
    <span class="swatch-row">
      <span class="swatch" style="background:{ACCENT};opacity:0.10"></span>
      <span class="swatch" style="background:{ACCENT};opacity:0.35"></span>
      <span class="swatch" style="background:{ACCENT};opacity:0.70"></span>
      <span class="swatch" style="background:{ACCENT};opacity:0.95"></span>
      <span>quieter ←→ hotter</span>
    </span>
    <span>· numbers: 0–100 mean momentum</span>
    <span>· dashed: N&lt;3 (low confidence)</span>
  </div>
</section>

<section>
  <div class="section-head">
    <h2 class="section-num"><span class="roman">V</span>What's next.</h2>
    <p class="section-sub">Step 3 of 6 · funding layer</p>
  </div>
  <p class="pullquote">
    Cross-industry is still the largest row at {cross_n} of {n} —
    Step 4 cracks that open into sub-sectors. Step 3 next: fill the
    funding column and add a third view to this toggle. Step 5
    surfaces problem themes and pulls findings up to the top of this
    page.
  </p>
</section>

<footer>
  <span>YC AI Momentum Heatmap</span>
  <span>Cohort {today} · {n} companies · Step 2 of 6</span>
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
<script>{JS}</script>
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
