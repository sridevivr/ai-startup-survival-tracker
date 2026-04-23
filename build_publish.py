"""
Recruiter-facing publish page.

Renders `output/publish.html` and a copy at root-level `index.html`.
One self-contained file, no external CSS or JS.

Page structure:

    1. Header with title, boxed lede, meta, optional delta banner
    2. Intro narrative. Defines sector, function, and what Cross-industry means.
    3. Today's snapshot. Status donut + legend.
    4. Sector × Function heatmap. Short horizontal headers, clear purpose.
    5. Per-status sections. Each one contains:
        - Two mini bar charts (sector breakdown and function breakdown)
        - A top-5 scorecard of strongest-scoring companies
        - An auto-generated insight paragraph from the data
        - A filterable, collapsible company list with sector + function dropdowns
    6. Delta section. Only renders when a diff report exists.
    7. Footer.

Design notes:

    * No em dashes anywhere. Commas, periods, parentheses only.
    * Heatmap column headers stay horizontal using short function labels.
      The full name is available via the tooltip on each cell.
    * Each bucket gets its own client-side filter state, implemented with
      a small shared JS helper and per-bucket data attributes.
    * The "insight" text is generated from the bucket's data at build time,
      so it refreshes each week when the pipeline runs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import html
import json
import math
import os
import re
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path


# --------------------------------------------------------------------------
# Taxonomies
# --------------------------------------------------------------------------

STATUS_ORDER = [
    "Thriving", "Healthy", "Watchlist", "Dormant",
    "Likely Dead", "Pivoted / Absorbed", "Not Yet Enriched",
]
STATUS_COLORS = {
    "Thriving":           "#0b8a3e",
    "Healthy":            "#4bb86a",
    "Watchlist":          "#d8a24a",
    "Dormant":            "#a07a3a",
    "Likely Dead":        "#b34b3f",
    "Pivoted / Absorbed": "#6a6a9e",
    "Not Yet Enriched":   "#888888",
}
STATUS_BLURBS = {
    "Thriving":           "Clean signals across the board. Live site, fresh Wayback, active GitHub, hiring, recent trusted press.",
    "Healthy":            "Most signals positive, one or two quiet. The bulk of a working cohort sits here.",
    "Watchlist":          "Ambiguous middle. Live sites, patchy coverage. Month-over-month delta is what matters, not today's score.",
    "Dormant":            "Multiple negative signals but not over the cliff. Often late-stage quiet before an acquihire or wind-down.",
    "Likely Dead":        "Score under 25, or a trusted death headline in the last 180 days, or a curated shutdown marker. Triage, not verdict.",
    "Pivoted / Absorbed": "Curated note captured an acquihire, acquisition, licensing deal, or rebrand. The brand is gone even if the website isn't.",
    "Not Yet Enriched":   "Row exists in the seed list but no signals have resolved yet.",
}

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
# Short labels for tight spaces like heatmap column headers.
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
FUNCTION_COLORS = {
    "Foundation Models":       "#6a4e9e",
    "ML Infrastructure":       "#4e86a3",
    "Data Infrastructure":     "#6a8ab0",
    "AI Agent":                "#3d7a4e",
    "Copilot / Assistant":     "#d8a24a",
    "Generative Product":      "#9e6a4e",
    "Analytics & Decisioning": "#5a6a80",
    "Research Lab":            "#7a7a7a",
}

SECTOR_ORDER = [
    "Cross-industry", "Healthcare", "Finance", "Consumer", "Customer Support",
    "Engineering", "E-commerce", "Security", "Legal", "Logistics",
    "HR", "Education", "Real Estate", "Gaming", "ClimateTech",
]
SECTOR_COLORS = {
    "Cross-industry":        "#5a6a80",
    "Healthcare":        "#4bb86a",
    "Finance":           "#3d7a4e",
    "Consumer":          "#9e6a4e",
    "Customer Support":  "#6a4e9e",
    "Engineering":       "#7a7a7a",
    "E-commerce":        "#d8a24a",
    "Security":          "#b34b3f",
    "Legal":             "#6a6a9e",
    "Logistics":         "#4e86a3",
    "HR":                "#b07a4e",
    "Education":         "#6a8ab0",
    "Real Estate":       "#8e7a3f",
    "Gaming":            "#9e4e8a",
    "ClimateTech":       "#0b8a3e",
}


# --------------------------------------------------------------------------
# Markdown renderer (we only parse VC_BRIEF.md and diff reports)
# --------------------------------------------------------------------------

_NUM_CELL = re.compile(r"^\s*[+\-]?\d[\d,.]*\s*%?\s*$|^-$")


def _td_class(raw_cell: str) -> str:
    return ' class="num"' if _NUM_CELL.match(raw_cell.strip()) else ""


def _inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
    return text


def markdown_to_html(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped in ("---", "***"):
            out.append("<hr/>")
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", stripped)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            i += 1
            continue
        if "|" in stripped and i + 1 < n and re.match(r"^\s*\|?[\s:\-\|]+\|?\s*$", lines[i + 1]):
            header_cells = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2
            rows: list[list[str]] = []
            while i < n and "|" in lines[i].strip():
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            ncols = len(header_cells)
            numeric_col = [False] * ncols
            for ci in range(ncols):
                hits = sum(1 for r in rows if ci < len(r) and _NUM_CELL.match(r[ci].strip()))
                numeric_col[ci] = rows and hits >= max(1, len(rows) // 2 + 1)
            NA = ' class="num"'
            out.append('<div class="table-wrap"><table>')
            th = []
            for ci, c in enumerate(header_cells):
                th.append(f"<th{NA if numeric_col[ci] else ''}>{_inline(c)}</th>")
            out.append("<thead><tr>" + "".join(th) + "</tr></thead>")
            out.append("<tbody>")
            for r in rows:
                td = []
                for ci, c in enumerate(r):
                    attr = NA if (ci < ncols and numeric_col[ci]) else ""
                    td.append(f"<td{attr}>{_inline(c)}</td>")
                out.append("<tr>" + "".join(td) + "</tr>")
            out.append("</tbody></table></div>")
            continue
        if re.match(r"^[-*]\s+", stripped):
            out.append("<ul>")
            bullet_re = re.compile(r"^\s*[-*]\s+")
            while i < n and bullet_re.match(lines[i]):
                item = bullet_re.sub("", lines[i])
                out.append(f"<li>{_inline(item)}</li>")
                i += 1
            out.append("</ul>")
            continue
        buf: list[str] = []
        while i < n and lines[i].strip() and not lines[i].strip().startswith("#"):
            if re.match(r"^(\s*[-*]\s+|\s*\d+\.\s+|>|---)", lines[i].strip()):
                break
            if "|" in lines[i] and i + 1 < n and re.match(r"^\s*\|?[\s:\-\|]+\|?\s*$", lines[i + 1]):
                break
            buf.append(lines[i].strip())
            i += 1
        if buf:
            out.append(f"<p>{_inline(' '.join(buf))}</p>")
    return "\n".join(out)


# --------------------------------------------------------------------------
# Charts
# --------------------------------------------------------------------------


def donut_chart(counts: "OrderedDict[str, int]", colors: dict, size: int = 260) -> str:
    total = sum(counts.values()) or 1
    cx = cy = size / 2
    r_out = size / 2 - 10
    r_in = r_out * 0.62
    parts: list[str] = []
    start = -90.0
    for key, n in counts.items():
        if n <= 0:
            continue
        frac = n / total
        end = start + frac * 360.0
        large = 1 if (end - start) > 180 else 0
        sx = cx + r_out * math.cos(math.radians(start))
        sy = cy + r_out * math.sin(math.radians(start))
        ex = cx + r_out * math.cos(math.radians(end))
        ey = cy + r_out * math.sin(math.radians(end))
        sx2 = cx + r_in * math.cos(math.radians(end))
        sy2 = cy + r_in * math.sin(math.radians(end))
        ex2 = cx + r_in * math.cos(math.radians(start))
        ey2 = cy + r_in * math.sin(math.radians(start))
        d = (f"M {sx:.2f} {sy:.2f} "
             f"A {r_out:.2f} {r_out:.2f} 0 {large} 1 {ex:.2f} {ey:.2f} "
             f"L {sx2:.2f} {sy2:.2f} "
             f"A {r_in:.2f} {r_in:.2f} 0 {large} 0 {ex2:.2f} {ey2:.2f} Z")
        color = colors.get(key, "#888")
        parts.append(
            f'<path d="{d}" fill="{color}" stroke="#fff" stroke-width="1">'
            f'<title>{html.escape(key)}: {n} ({frac*100:.1f}%)</title></path>'
        )
        start = end
    center = (
        f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" '
        f'font-size="32" font-weight="700" fill="#1a1a1a">{total}</text>'
        f'<text x="{cx}" y="{cy + 18}" text-anchor="middle" '
        f'font-size="12" fill="#666">companies</text>'
    )
    return (f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
            f'xmlns="http://www.w3.org/2000/svg">{"".join(parts)}{center}</svg>')


def sector_function_heatmap(companies: list[dict]) -> str:
    """Rows are sectors (desc by total), columns are functions (desc by total)."""
    matrix: dict[tuple[str, str], int] = defaultdict(int)
    sector_totals: Counter[str] = Counter()
    function_totals: Counter[str] = Counter()
    for c in companies:
        s = (c.get("sector") or "").strip() or "—"
        f = (c.get("function") or "").strip() or "—"
        matrix[(s, f)] += 1
        sector_totals[s] += 1
        function_totals[f] += 1

    sectors = [s for s, _ in sector_totals.most_common() if s != "—"]
    functions = [f for f, _ in function_totals.most_common() if f != "—"]
    if not sectors or not functions:
        return "<p>No sector/function data yet.</p>"

    row_h, col_w = 34, 110
    pad_left, pad_top = 160, 64
    width = pad_left + col_w * len(functions) + 20
    height = pad_top + row_h * len(sectors) + 40

    cell_max = max(matrix.values()) or 1

    parts: list[str] = []
    parts.append(
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI, system-ui, sans-serif">'
    )
    # Column headers, horizontal, using short labels
    for j, f in enumerate(functions):
        x = pad_left + j * col_w + (col_w - 6) / 2
        label = FUNCTION_SHORT.get(f, f)
        parts.append(
            f'<text x="{x}" y="{pad_top - 14}" text-anchor="middle" '
            f'font-size="12" fill="#1a2b1a" font-weight="600">{html.escape(label)}</text>'
            f'<text x="{x}" y="{pad_top - 2}" text-anchor="middle" '
            f'font-size="10" fill="#5a6a5a">({function_totals[f]})</text>'
        )
    for i, s in enumerate(sectors):
        y = pad_top + i * row_h
        parts.append(
            f'<text x="{pad_left - 12}" y="{y + row_h / 2 + 4}" text-anchor="end" '
            f'font-size="12" fill="#1a2b1a" font-weight="600">{html.escape(s)} '
            f'<tspan fill="#5a6a5a" font-weight="400">({sector_totals[s]})</tspan></text>'
        )
        for j, f in enumerate(functions):
            x = pad_left + j * col_w
            cnt = matrix.get((s, f), 0)
            if cnt == 0:
                parts.append(
                    f'<rect x="{x}" y="{y + 3}" width="{col_w - 6}" '
                    f'height="{row_h - 6}" fill="#f2f7ee" stroke="#d5e3cf"/>'
                )
                continue
            alpha = 0.28 + 0.72 * math.sqrt(cnt / cell_max)
            color = FUNCTION_COLORS.get(f, "#666")
            text_color = "#fff" if alpha >= 0.55 else "#1a2b1a"
            parts.append(
                f'<rect x="{x}" y="{y + 3}" width="{col_w - 6}" '
                f'height="{row_h - 6}" fill="{color}" fill-opacity="{alpha:.2f}" '
                f'stroke="{color}" stroke-opacity="0.45">'
                f'<title>{html.escape(s)} · {html.escape(f)}: {cnt}</title></rect>'
                f'<text x="{x + (col_w - 6) / 2}" y="{y + row_h / 2 + 4}" '
                f'text-anchor="middle" font-size="13" font-weight="600" '
                f'fill="{text_color}">{cnt}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def css_bar_chart(counts: dict, colors: dict, max_bars: int = 8) -> str:
    """Compact horizontal CSS bar chart for per-bucket breakdowns."""
    items = sorted(counts.items(), key=lambda kv: -kv[1])[:max_bars]
    if not items:
        return '<p class="bar-empty">No data.</p>'
    max_val = max(v for _, v in items) or 1
    rows_html = []
    for label, n in items:
        width_pct = max(4.0, (n / max_val) * 100.0)
        color = colors.get(label, "#888")
        rows_html.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{html.escape(label)}</span>'
            f'<div class="bar-track">'
            f'<div class="bar-fill" style="width: {width_pct:.1f}%; background: {color}"></div>'
            f'</div>'
            f'<span class="bar-count">{n}</span>'
            f'</div>'
        )
    return f'<div class="bars">{"".join(rows_html)}</div>'


# --------------------------------------------------------------------------
# Per-bucket content
# --------------------------------------------------------------------------


def _score_str(c: dict) -> str:
    v = c.get("survival_score")
    try:
        return f"{float(v):.1f}" if v is not None else "—"
    except (TypeError, ValueError):
        return "—"


def _strip_emdash(s: str) -> str:
    """Replace em-dashes and en-dashes with plain commas for readability."""
    return s.replace("\u2014", ",").replace("\u2013", "-")


def _pick_headline(c: dict) -> str:
    notes = c.get("notes") or []
    for n in notes:
        if n:
            return _strip_emdash(str(n))
    death = c.get("news_death_headline")
    if death:
        return _strip_emdash(f"News: {death}")
    health = c.get("news_health_headline")
    if health:
        return _strip_emdash(f"News: {health}")
    return ""


def _company_card(c: dict) -> str:
    name = html.escape(c.get("name", ""))
    website = c.get("website") or ""
    score_s = _score_str(c)
    sector = c.get("sector") or ""
    function = c.get("function") or ""
    sector_color = SECTOR_COLORS.get(sector, "#888")
    function_color = FUNCTION_COLORS.get(function, "#888")
    headline = html.escape(_pick_headline(c)[:160])
    site_html = (
        f'<a href="{html.escape(website)}" target="_blank" rel="noopener noreferrer">{name}</a>'
        if website else name
    )
    tags = ""
    if sector:
        tags += (f'<span class="sec-tag" style="--sec-color:{sector_color}">'
                 f'{html.escape(sector)}</span>')
    if function:
        tags += (f'<span class="func-tag" style="--func-color:{function_color}">'
                 f'{html.escape(function)}</span>')
    note_html = f'<div class="company-note">{headline}</div>' if headline else ""
    return (
        f'<div class="company" '
        f'data-sector="{html.escape(sector)}" '
        f'data-function="{html.escape(function)}">'
        f'<div class="company-head">'
        f'<span class="company-name">{site_html}</span>'
        f'<span class="company-score">{score_s}</span>'
        f'</div>'
        f'<div class="company-tags">{tags}</div>'
        f'{note_html}'
        f'</div>'
    )


def _bucket_insight(status: str, rows: list[dict], cohort_total: int,
                    cohort_sector_counts: Counter, cohort_function_counts: Counter) -> str:
    """Build a data-driven one-paragraph insight for the bucket."""
    if not rows:
        return ""
    total = len(rows)
    sector_counts: Counter[str] = Counter(r.get("sector", "") or "—" for r in rows)
    function_counts: Counter[str] = Counter(r.get("function", "") or "—" for r in rows)

    top_sec, top_sec_n = sector_counts.most_common(1)[0]
    top_fn, top_fn_n = function_counts.most_common(1)[0]

    pct_sec = 100 * top_sec_n / total
    pct_fn = 100 * top_fn_n / total

    # Over- or under-representation vs overall cohort
    base_sec_pct = (100 * cohort_sector_counts.get(top_sec, 0) / cohort_total) if cohort_total else 0
    base_fn_pct = (100 * cohort_function_counts.get(top_fn, 0) / cohort_total) if cohort_total else 0

    sec_skew = ""
    if base_sec_pct > 0:
        if pct_sec - base_sec_pct >= 10:
            sec_skew = f" This is higher than the cohort-wide share of {base_sec_pct:.0f}%."
        elif base_sec_pct - pct_sec >= 10:
            sec_skew = f" This is lower than the cohort-wide share of {base_sec_pct:.0f}%."

    fn_skew = ""
    if base_fn_pct > 0:
        if pct_fn - base_fn_pct >= 10:
            fn_skew = f" That is a heavier tilt than the cohort average of {base_fn_pct:.0f}%."

    body = (
        f"{status} is dominated by <strong>{html.escape(top_sec)}</strong> companies "
        f"({top_sec_n} of {total}, {pct_sec:.0f}%), and the most common function is "
        f"<strong>{html.escape(top_fn)}</strong> ({top_fn_n}, {pct_fn:.0f}%).{sec_skew}{fn_skew}"
    )

    # Status-specific addenda to keep each bucket's insight distinct.
    if status == "Thriving" and "Foundation Models" in function_counts:
        body += (
            f" Every Foundation Models company that resolved signals sits at or near the top of "
            f"the distribution, which tracks the capital concentration at the model layer."
        )
    elif status == "Watchlist":
        body += (
            " This is the bucket most worth watching week over week. Score deltas of more than ten "
            "points between snapshots are usually where the real story lives."
        )
    elif status == "Likely Dead":
        body += (
            " Verify before acting on any single row. The score is a triage signal, "
            "and labels can move after one month of hiring or press activity."
        )
    elif status == "Pivoted / Absorbed":
        body += (
            " The curated note on each card names the corporate event. "
            "Acquihires dominate this bucket."
        )

    return f'<p>{body}</p>'


def _top5(rows: list[dict]) -> str:
    scored = [r for r in rows if r.get("survival_score") is not None]
    scored.sort(key=lambda r: -float(r.get("survival_score") or 0))
    top = scored[:5]
    if not top:
        return ""
    cells: list[str] = []
    for rank, r in enumerate(top, start=1):
        name = html.escape(r.get("name", ""))
        website = r.get("website") or ""
        if website:
            name = (f'<a href="{html.escape(website)}" target="_blank" '
                    f'rel="noopener noreferrer">{name}</a>')
        score = _score_str(r)
        sector = html.escape(r.get("sector") or "—")
        function = html.escape(r.get("function") or "—")
        cells.append(
            f'<tr>'
            f'<td class="rank">{rank}</td>'
            f'<td>{name}</td>'
            f'<td class="num">{score}</td>'
            f'<td>{sector}</td>'
            f'<td>{function}</td>'
            f'</tr>'
        )
    return (
        f'<div class="scorecard">'
        f'<h4>Top 5 in this bucket</h4>'
        f'<table><thead><tr>'
        f'<th class="rank">#</th><th>Company</th>'
        f'<th class="num">Score</th><th>Sector</th><th>Function</th>'
        f'</tr></thead><tbody>'
        f'{"".join(cells)}'
        f'</tbody></table>'
        f'</div>'
    )


def _bucket_section(status: str, rows: list[dict], bucket_id: str,
                    cohort_total: int,
                    cohort_sector_counts: Counter,
                    cohort_function_counts: Counter) -> str:
    if not rows:
        return ""
    rows_sorted = sorted(rows, key=lambda r: -float(r.get("survival_score") or 0))
    sector_counts = Counter(r.get("sector", "") or "—" for r in rows_sorted)
    function_counts = Counter(r.get("function", "") or "—" for r in rows_sorted)

    color = STATUS_COLORS.get(status, "#888")
    blurb = STATUS_BLURBS.get(status, "")

    header = (
        f'<div class="bucket-header" style="--bucket-color:{color}">'
        f'<div class="bucket-title-row">'
        f'<span class="bucket-dot" style="background:{color}"></span>'
        f'<h3 class="bucket-title">{html.escape(status)}</h3>'
        f'<span class="bucket-count">{len(rows_sorted)}</span>'
        f'</div>'
        f'<p class="bucket-blurb">{html.escape(blurb)}</p>'
        f'</div>'
    )

    sector_bars = css_bar_chart(sector_counts, SECTOR_COLORS)
    function_bars = css_bar_chart(function_counts, FUNCTION_COLORS)

    charts_block = (
        f'<div class="bucket-charts">'
        f'<div class="mini-chart"><h4>By sector</h4>{sector_bars}</div>'
        f'<div class="mini-chart"><h4>By function</h4>{function_bars}</div>'
        f'</div>'
    )

    top5_block = _top5(rows_sorted)
    insight_block = (
        f'<div class="bucket-insight"><h4>What the data shows</h4>'
        f'{_bucket_insight(status, rows_sorted, cohort_total, cohort_sector_counts, cohort_function_counts)}'
        f'</div>'
    )

    # Filter dropdowns (sector, function) scoped to this bucket
    sectors = ["All"] + [s for s, _ in sector_counts.most_common()]
    functions = ["All"] + [f for f, _ in function_counts.most_common()]

    def _options(items):
        return "".join(f'<option value="{html.escape(v)}">{html.escape(v)}</option>' for v in items)

    filter_block = (
        f'<div class="bucket-filter">'
        f'<label>Sector <select data-role="sector-filter" data-bucket="{bucket_id}">'
        f'{_options(sectors)}</select></label>'
        f'<label>Function <select data-role="function-filter" data-bucket="{bucket_id}">'
        f'{_options(functions)}</select></label>'
        f'<button class="reset-btn" data-bucket="{bucket_id}">Reset</button>'
        f'<span class="filter-visible-count" data-bucket="{bucket_id}">'
        f'Showing {len(rows_sorted)} of {len(rows_sorted)}</span>'
        f'</div>'
    )

    cards = "".join(_company_card(r) for r in rows_sorted)

    list_block = (
        f'<details class="bucket-list"{" open" if status in ("Thriving", "Pivoted / Absorbed") else ""}>'
        f'<summary>All {len(rows_sorted)} companies in {html.escape(status)}</summary>'
        f'<div class="company-grid" id="{bucket_id}-grid">{cards}</div>'
        f'</details>'
    )

    return (
        f'<section class="bucket" id="{bucket_id}">'
        f'{header}'
        f'{charts_block}'
        f'{top5_block}'
        f'{insight_block}'
        f'{filter_block}'
        f'{list_block}'
        f'</section>'
    )


# --------------------------------------------------------------------------
# Delta helpers
# --------------------------------------------------------------------------


def _find_latest_diff(root: str = "snapshots/diffs") -> tuple[str | None, str | None]:
    if not os.path.isdir(root):
        return None, None
    files = sorted(glob.glob(os.path.join(root, "????-??-??.md")))
    if not files:
        return None, None
    latest = files[-1]
    return latest, os.path.splitext(os.path.basename(latest))[0]


# --------------------------------------------------------------------------
# Intro narrative
# --------------------------------------------------------------------------


def _narrative_intro(counts: "OrderedDict[str, int]", companies: list[dict]) -> str:
    total = sum(counts.values())
    thriving = counts.get("Thriving", 0)
    healthy = counts.get("Healthy", 0)
    watchlist = counts.get("Watchlist", 0)
    dead = counts.get("Likely Dead", 0)
    pivoted = counts.get("Pivoted / Absorbed", 0)
    dormant = counts.get("Dormant", 0)

    # Cohort-level sector/function concentrations for the closing paragraph.
    sec = Counter(c.get("sector", "") for c in companies if c.get("sector"))
    fn = Counter(c.get("function", "") for c in companies if c.get("function"))
    sec_h = sec.get("Cross-industry", 0)
    sec_pct_h = 100 * sec_h / total if total else 0
    top_sector_nonh = next(((s, n) for s, n in sec.most_common() if s and s != "Cross-industry"),
                           ("Healthcare", 0))
    top_fn = fn.most_common(1)[0] if fn else ("AI Agent", 0)

    # Data-driven headline. Pick the finding with the most narrative punch.
    watchlist_pct = 100 * watchlist / total if total else 0
    headline = (
        f"Most AI startups from the 2023 to 2025 wave are neither thriving nor dead. "
        f"{watchlist} of the {total} tracked companies ({watchlist_pct:.0f}%) sit in the "
        f"Watchlist middle, where the monthly delta is the real signal rather than today's score."
    )

    parts: list[str] = []

    # Her requested opening, kept close to the wording she gave.
    parts.append(
        "<p>Lately it feels like there is a new AI startup getting funded every day. "
        "The industry is evolving so quickly that I felt like I needed to find a way to "
        "make sense of what's working and what isn't.</p>"
    )
    parts.append(
        "<p>This started off as a tool to figure out where the startups that received "
        "funding from 2023 to 2025 are right now, and to use that to understand if there "
        "are larger shifts taking place.</p>"
    )
    parts.append(
        "<p>The companies are mostly YC incubees. Each company is scored on seven public "
        "signals (website uptime, Wayback freshness, blog cadence, GitHub activity, hiring "
        "pulse, trusted news coverage, and curated notes), and the score maps to one of six "
        "status buckets from Thriving at the top to Likely Dead at the bottom.</p>"
    )
    parts.append("<p>Every company also carries two classification tags:</p>")
    parts.append(
        "<ul>"
        "<li><strong>Sector</strong> names the vertical the company serves, such as "
        "Healthcare, Finance, Legal, Education, or Real Estate.</li>"
        "<li>When a company's product is sold across verticals, for example developer "
        "tooling, agent infrastructure, or general LLM platforms, the sector is "
        "<strong>Cross-industry</strong>.</li>"
        "<li><strong>Function</strong> names where the company sits in the AI stack: "
        "Foundation Models, ML Infrastructure, Data Infrastructure, AI Agent, Copilot or "
        "Assistant, Generative Product, Analytics and Decisioning, or Research Lab.</li>"
        "</ul>"
    )
    parts.append("<p>The shape of the cohort today:</p>")
    parts.append(
        "<ul>"
        f"<li>{thriving} Thriving</li>"
        f"<li>{healthy} Healthy</li>"
        f"<li>{watchlist} on the Watchlist</li>"
        f"<li>{dormant} Dormant</li>"
        f"<li>{dead} Likely Dead</li>"
        f"<li>{pivoted} Pivoted or Absorbed</li>"
        f"<li>Most of the change between weekly runs happens inside the Watchlist, "
        f"which is why the month-over-month delta is the real story.</li>"
        "</ul>"
    )

    # Headline / Insight callout
    parts.append(
        f'<div class="headline-callout">'
        f'<h3>Headline</h3>'
        f'<p>{headline}</p>'
        f'</div>'
    )

    # How to read the rest of the page
    parts.append("<h3>How to read this page</h3>")
    parts.append(
        "<ul>"
        "<li><strong>Today's snapshot</strong>: a ring chart of all "
        f"{total} companies broken down by status bucket, with a matching legend.</li>"
        "<li><strong>Sector × Function</strong>: a grid showing which sectors pair with "
        "which functions across the cohort. Darker cells are more companies.</li>"
        "<li><strong>By status</strong>: six sections, one per bucket. Each section "
        "contains two bar charts (sector and function mix inside the bucket), a top 5 "
        "scorecard of the strongest-scoring companies, a short auto-generated insight "
        "paragraph, and a filterable company list with dropdowns for sector and function.</li>"
        "</ul>"
    )
    parts.append(
        '<p>The full methodology, code, and raw dataset are in the '
        '<a href="https://github.com/sridevivr/ai-startup-survival-tracker">GitHub repo</a>.</p>'
    )
    return "".join(parts)


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------


def build(signals_path: str, out_path: str, index_path: str | None,
          diffs_dir: str = "snapshots/diffs") -> None:
    with open(signals_path, encoding="utf-8") as f:
        companies: list[dict] = json.load(f)

    raw_counts = Counter(c.get("status", "") for c in companies)
    counts: OrderedDict[str, int] = OrderedDict()
    for s in STATUS_ORDER:
        counts[s] = raw_counts.get(s, 0)

    diff_path, diff_date = _find_latest_diff(diffs_dir)
    diff_html = ""
    if diff_path:
        with open(diff_path, encoding="utf-8") as f:
            md = re.sub(r"^#\s+.*\n", "", f.read(), count=1)
        diff_html = markdown_to_html(md)

    intro_html = _narrative_intro(counts, companies)

    cohort_total = len(companies)
    cohort_sector_counts = Counter((c.get("sector") or "—") for c in companies)
    cohort_function_counts = Counter((c.get("function") or "—") for c in companies)

    by_status: dict[str, list[dict]] = defaultdict(list)
    for c in companies:
        by_status[c.get("status", "")].append(c)

    bucket_sections: list[str] = []
    for idx, status in enumerate(STATUS_ORDER):
        rows = by_status.get(status, [])
        if not rows:
            continue
        bid = "bucket-" + re.sub(r"[^a-z0-9]+", "-", status.lower()).strip("-")
        bucket_sections.append(
            _bucket_section(status, rows, bid,
                            cohort_total, cohort_sector_counts, cohort_function_counts)
        )

    donut_svg = donut_chart(counts, STATUS_COLORS)
    heatmap_svg = sector_function_heatmap(companies)

    total = sum(counts.values())
    summary = (
        f"Of {total} AI companies tracked in the 2023 and later cohort, "
        f"{counts['Thriving']} score as Thriving, {counts['Likely Dead']} Likely Dead, "
        f"{counts['Pivoted / Absorbed']} Pivoted or Absorbed, and {counts['Watchlist']} "
        f"sit in the ambiguous Watchlist middle where the interesting question is the "
        f"month-over-month delta, not today's score."
    )

    refreshed = dt.datetime.utcnow().strftime("%B %d, %Y")

    banner_html = ""
    if diff_html:
        banner_html = (
            f'<aside class="banner"><strong>Weekly delta</strong>. '
            f'<a href="#delta">What changed through {html.escape(diff_date or "latest")}</a>.'
            f'</aside>'
        )

    status_legend = []
    for s in STATUS_ORDER:
        if counts.get(s, 0) <= 0:
            continue
        status_legend.append(
            f'<li><span class="swatch" style="background:{STATUS_COLORS[s]}"></span>'
            f'<span class="label">{html.escape(s)}</span>'
            f'<span class="count">{counts.get(s, 0)}</span></li>'
        )

    # Hero stat cards — four big numbers up top, serif display font.
    hero_stats_html = (
        '<div class="hero-stats">'
        f'<div class="stat-card stat-neutral">'
        f'<div class="stat-num">{total}</div>'
        f'<div class="stat-label">Companies tracked</div></div>'
        f'<div class="stat-card stat-accent" style="--stat-color:{STATUS_COLORS["Thriving"]}">'
        f'<div class="stat-num">{counts["Thriving"]}</div>'
        f'<div class="stat-label">Thriving</div></div>'
        f'<div class="stat-card stat-accent" style="--stat-color:{STATUS_COLORS["Watchlist"]}">'
        f'<div class="stat-num">{counts["Watchlist"]}</div>'
        f'<div class="stat-label">On the Watchlist</div></div>'
        f'<div class="stat-card stat-accent" style="--stat-color:{STATUS_COLORS["Likely Dead"]}">'
        f'<div class="stat-num">{counts["Likely Dead"]}</div>'
        f'<div class="stat-label">Likely Dead</div></div>'
        '</div>'
    )

    # Heatmap legend strip
    heatmap_legend_html = (
        '<div class="heatmap-legend">'
        '<span class="legend-label">fewer</span>'
        '<div class="legend-scale">'
        '<span style="background: rgba(61,122,78,0.25)"></span>'
        '<span style="background: rgba(61,122,78,0.45)"></span>'
        '<span style="background: rgba(61,122,78,0.65)"></span>'
        '<span style="background: rgba(61,122,78,0.85)"></span>'
        '<span style="background: rgba(61,122,78,1.0)"></span>'
        '</div>'
        '<span class="legend-label">more</span>'
        '</div>'
    )

    # --------- page template ---------
    page = PAGE_TEMPLATE.format(
        summary=html.escape(summary),
        refreshed=refreshed,
        banner_html=banner_html,
        intro_html=intro_html,
        hero_stats_html=hero_stats_html,
        donut_svg=donut_svg,
        heatmap_svg=heatmap_svg,
        heatmap_legend_html=heatmap_legend_html,
        status_legend="".join(status_legend),
        bucket_sections="".join(bucket_sections),
        delta_block=(
            '<hr class="section-rule"/>'
            '<div class="section-head" id="delta">'
            '<span class="eyebrow">Section 04 · Weekly delta</span>'
            '<h2>What changed this week</h2></div>'
            f'<div class="delta-section">{diff_html}</div>'
            if diff_html else ""
        ),
    )

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(page, encoding="utf-8")
    print(f"Wrote {out_path}")
    if index_path:
        Path(index_path).write_text(page, encoding="utf-8")
        print(f"Wrote {index_path} (copy for GitHub Pages root)")


# --------------------------------------------------------------------------
# Page template (double braces escape for .format())
# --------------------------------------------------------------------------

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>AI Startup Survival Tracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Lora:wght@500;600;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --fg: #1a2b1a;
    --muted: #5a6a5a;
    --bg: #eef6ea;
    --card: #ffffff;
    --border: #d5e3cf;
    --accent: #3d7a4e;
    --accent-2: #b05a3c;  /* muted terracotta, contrast accent */
    --display: "Lora", Georgia, "Times New Roman", serif;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
    color: var(--fg);
    background: var(--bg);
    line-height: 1.55;
    font-size: 16px;
  }}
  .container {{ max-width: 1080px; margin: 0 auto; padding: 40px 24px 80px; }}
  h1 {{ font-family: var(--display); font-weight: 700; font-size: 2.6rem; margin: 0 0 8px; letter-spacing: -0.01em; }}
  h2 {{ font-size: 1.4rem; margin: 44px 0 14px; letter-spacing: -0.01em; }}
  h3 {{ font-size: 1.15rem; margin: 20px 0 6px; }}
  h4 {{ font-size: 0.95rem; margin: 14px 0 8px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }}
  p {{ margin: 0 0 14px; }}
  a {{ color: var(--accent); }}
  .lede {{
    font-size: 1.05rem; color: var(--fg);
    background: var(--card); padding: 18px 22px;
    border-radius: 8px; margin: 8px 0 16px; line-height: 1.6;
  }}
  .meta {{ font-size: 0.85rem; color: var(--muted); margin-bottom: 28px; }}
  .banner {{
    background: #fff4d6; border: 1px solid #e7d08a;
    padding: 10px 14px; border-radius: 6px; margin-bottom: 28px;
    font-size: 0.95rem;
  }}
  /* Hero stat cards */
  .hero-stats {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin: 16px 0 28px;
  }}
  .stat-card {{
    background: var(--card);
    border-radius: 10px;
    padding: 18px 20px;
    box-shadow: 0 1px 3px rgba(40,60,30,.06);
    border-left: 4px solid var(--stat-color, var(--accent));
  }}
  .stat-card.stat-neutral {{ border-left-color: var(--accent); }}
  .stat-num {{
    font-family: var(--display);
    font-size: 2.6rem;
    font-weight: 700;
    line-height: 1;
    color: var(--stat-color, var(--fg));
    font-variant-numeric: tabular-nums;
    margin-bottom: 4px;
  }}
  .stat-card.stat-neutral .stat-num {{ color: var(--fg); }}
  .stat-label {{
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.72rem;
    font-weight: 600;
  }}
  @media (max-width: 720px) {{
    .hero-stats {{ grid-template-columns: repeat(2, 1fr); }}
  }}

  /* Heatmap legend strip */
  .heatmap-legend {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 12px 0 6px;
    font-size: 0.78rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }}
  .heatmap-legend .legend-label {{ flex: none; }}
  .heatmap-legend .legend-scale {{
    display: inline-flex;
    gap: 1px;
    border-radius: 4px;
    overflow: hidden;
  }}
  .heatmap-legend .legend-scale span {{
    width: 28px; height: 14px; display: inline-block;
  }}

  /* Author / byline card in footer */
  .author-card {{
    background: var(--card);
    border-radius: 10px;
    padding: 18px 22px;
    margin: 30px 0 10px;
    box-shadow: 0 1px 3px rgba(40,60,30,.06);
  }}
  .author-card h4 {{
    margin: 0 0 6px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.74rem;
    color: var(--accent-2);
  }}
  .author-card p {{
    margin: 0 0 6px;
    color: var(--fg);
  }}
  .author-card p.bio {{ color: var(--muted); font-size: 0.92rem; }}
  .author-card a {{ color: var(--accent); }}

  .intro p, .intro ul {{ max-width: none; }}
  .intro ul {{ padding-left: 22px; margin: 6px 0 16px; }}
  .intro ul li {{ margin-bottom: 4px; }}
  .intro h3 {{ margin-top: 28px; font-size: 1.05rem; }}
  .headline-callout {{
    background: var(--card);
    border-left: 4px solid var(--accent-2);
    border-radius: 6px;
    padding: 14px 20px;
    margin: 24px 0;
    box-shadow: 0 1px 3px rgba(40,60,30,.05);
  }}
  .headline-callout h3 {{
    margin: 0 0 6px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.78rem;
    color: var(--accent-2);
  }}

  /* Section eyebrow labels and thin separator rules */
  .section-rule {{
    border: none;
    border-top: 1px solid var(--border);
    margin: 44px 0 18px;
  }}
  .eyebrow {{
    display: block;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.72rem;
    font-weight: 700;
    color: var(--accent-2);
    margin: 0 0 8px;
  }}
  .section-head h2 {{ margin-top: 0; }}

  /* Sticky left-hand table of contents (desktop only) */
  .toc {{
    position: fixed;
    left: calc(50% - 540px - 180px);
    top: 70px;
    width: 170px;
    z-index: 5;
    font-size: 0.82rem;
  }}
  .toc-label {{
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.68rem;
    color: var(--accent-2);
    font-weight: 700;
    margin-bottom: 10px;
  }}
  .toc ul {{ list-style: none; padding: 0; margin: 0; }}
  .toc li {{ margin: 0; }}
  .toc a {{
    display: block;
    padding: 6px 10px;
    color: var(--muted);
    text-decoration: none;
    border-left: 2px solid transparent;
    transition: all .15s ease;
    line-height: 1.3;
  }}
  .toc a:hover {{ color: var(--fg); border-left-color: var(--border); }}
  .toc a.active {{
    color: var(--accent);
    border-left-color: var(--accent);
    font-weight: 600;
  }}
  .toc .sub {{ padding-left: 10px; font-size: 0.78rem; }}
  @media (max-width: 1320px) {{ .toc {{ display: none; }} }}
  .headline-callout p {{
    margin: 0;
    font-size: 1.05rem;
    font-weight: 500;
  }}

  .snapshot {{
    display: flex; align-items: center; gap: 32px; flex-wrap: wrap;
    background: var(--card); border-radius: 10px;
    padding: 22px 26px; box-shadow: 0 1px 3px rgba(40,60,30,.06);
  }}
  .snapshot .legend {{ flex: 1; min-width: 260px; }}
  .legend ul {{ list-style: none; padding: 0; margin: 0; }}
  .legend li {{
    display: flex; align-items: center; padding: 4px 0;
    font-size: 0.95rem; gap: 10px;
  }}
  .legend .swatch {{ width: 14px; height: 14px; border-radius: 3px; flex: none; }}
  .legend .label {{ flex: 1; }}
  .legend .count {{ color: var(--muted); font-variant-numeric: tabular-nums; }}

  .heatmap-card {{
    background: var(--card); border-radius: 10px;
    padding: 22px 26px 12px; box-shadow: 0 1px 3px rgba(40,60,30,.06);
    overflow-x: auto;
  }}
  .heatmap-card h2 {{ margin-top: 0; }}
  .heatmap-card p.caption {{ color: var(--muted); font-size: 0.92rem; margin-bottom: 12px; max-width: 72ch; }}

  .bucket {{
    background: var(--card); border-radius: 10px;
    padding: 22px 26px; box-shadow: 0 1px 3px rgba(40,60,30,.06);
    margin-top: 24px;
    border-top: 4px solid var(--bucket-color, var(--accent));
  }}
  .bucket-title-row {{ display: flex; align-items: baseline; gap: 12px; margin-bottom: 2px; }}
  .bucket-dot {{ width: 14px; height: 14px; border-radius: 999px; display: inline-block; }}
  .bucket-title {{ margin: 0; font-size: 1.25rem; }}
  .bucket-count {{
    color: var(--muted); font-size: 1rem;
    font-variant-numeric: tabular-nums; font-weight: 600;
  }}
  .bucket-blurb {{
    color: var(--muted); font-size: 0.95rem;
    margin: 4px 0 18px; max-width: 72ch;
  }}

  .bucket-charts {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 24px;
    margin-bottom: 20px;
  }}
  @media (max-width: 720px) {{
    .bucket-charts {{ grid-template-columns: 1fr; }}
  }}
  .mini-chart h4 {{ margin-top: 0; }}
  .bars {{ display: flex; flex-direction: column; gap: 5px; }}
  .bar-row {{ display: grid; grid-template-columns: 130px 1fr 42px; gap: 8px; align-items: center; font-size: 0.88rem; }}
  .bar-label {{ color: var(--fg); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .bar-track {{ background: #f0f5ec; border-radius: 3px; height: 14px; overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 3px; }}
  .bar-count {{ color: var(--muted); font-variant-numeric: tabular-nums; text-align: right; }}

  .scorecard {{ margin-bottom: 18px; }}
  .scorecard table {{
    width: 100%; border-collapse: separate; border-spacing: 0;
    font-size: 0.92rem; background: #f7fbf4; border-radius: 8px;
    overflow: hidden; border: 1px solid var(--border);
  }}
  .scorecard thead th {{
    text-align: left; padding: 8px 12px; background: #dde9d3;
    font-size: 0.78rem; letter-spacing: .04em;
    text-transform: uppercase; border-bottom: 1px solid var(--border);
    color: var(--fg); font-weight: 600;
  }}
  .scorecard th.num, .scorecard td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .scorecard th.rank, .scorecard td.rank {{ width: 28px; text-align: center; color: var(--muted); }}
  .scorecard tbody td {{ padding: 8px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  .scorecard tbody tr:last-child td {{ border-bottom: none; }}
  .scorecard a {{ color: var(--fg); text-decoration: none; font-weight: 600; }}
  .scorecard a:hover {{ color: var(--accent); text-decoration: underline; }}

  .bucket-insight {{ margin-bottom: 18px; }}
  .bucket-insight p {{
    background: #f5faf1; border-left: 3px solid var(--accent);
    padding: 10px 14px; border-radius: 0 6px 6px 0;
    color: var(--fg); max-width: 72ch;
  }}

  .bucket-filter {{
    display: flex; flex-wrap: wrap; align-items: center;
    gap: 12px; margin: 14px 0 8px; font-size: 0.9rem;
  }}
  .bucket-filter label {{
    display: inline-flex; align-items: center; gap: 6px;
    color: var(--muted);
  }}
  .bucket-filter select {{
    padding: 4px 8px; border: 1px solid var(--border);
    border-radius: 6px; background: #f7fbf4;
    font-family: inherit; font-size: 0.9rem; color: var(--fg);
  }}
  .reset-btn {{
    padding: 4px 12px; border: 1px solid var(--border);
    border-radius: 6px; background: #ffffff; cursor: pointer;
    font-family: inherit; font-size: 0.85rem; color: var(--fg);
  }}
  .reset-btn:hover {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
  .filter-visible-count {{
    color: var(--muted); font-size: 0.85rem; margin-left: auto;
  }}

  .bucket-list > summary {{
    cursor: pointer; list-style: none;
    padding: 10px 6px; font-weight: 600; font-size: 0.95rem;
    display: flex; align-items: center; gap: 10px;
    color: var(--fg);
  }}
  .bucket-list > summary::-webkit-details-marker {{ display: none; }}
  .bucket-list > summary::before {{
    content: "›"; display: inline-block; transition: transform .15s ease;
    color: var(--muted); font-size: 1rem;
  }}
  .bucket-list[open] > summary::before {{ transform: rotate(90deg); }}

  .company-grid {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 10px; margin-top: 6px;
  }}
  .company.hidden {{ display: none; }}
  .company {{
    background: #f7fbf4; border: 1px solid var(--border);
    border-radius: 8px; padding: 10px 12px;
  }}
  .company-head {{
    display: flex; align-items: baseline; justify-content: space-between;
    gap: 8px; margin-bottom: 4px;
  }}
  .company-name {{ font-weight: 600; font-size: 0.95rem; }}
  .company-name a {{ color: var(--fg); text-decoration: none; }}
  .company-name a:hover {{ color: var(--accent); text-decoration: underline; }}
  .company-score {{
    color: var(--muted); font-variant-numeric: tabular-nums;
    font-weight: 500; font-size: 0.88rem;
  }}
  .company-tags {{ display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 4px; }}
  .sec-tag, .func-tag {{
    display: inline-block; font-size: 0.7rem;
    padding: 1px 7px; border-radius: 999px;
    color: #fff; font-weight: 600; letter-spacing: 0.02em;
  }}
  .sec-tag {{ background: var(--sec-color, #888); }}
  .func-tag {{ background: var(--func-color, #888); }}
  .company-note {{
    color: var(--muted); font-size: 0.82rem;
    margin-top: 6px; line-height: 1.4;
  }}

  .delta-section {{
    background: var(--card); border-radius: 10px;
    padding: 22px 26px; margin-top: 10px;
  }}
  .delta-section table {{
    border-collapse: separate; border-spacing: 0;
    width: 100%; font-size: 0.92rem;
    font-variant-numeric: tabular-nums;
  }}
  .table-wrap {{
    background: var(--card); border-radius: 8px;
    overflow: hidden; box-shadow: 0 1px 2px rgba(40,60,30,.05);
    margin: 14px 0;
  }}
  .table-wrap thead th {{
    text-align: left; padding: 11px 14px;
    background: #dde9d3; font-size: 0.8rem;
    font-weight: 600; letter-spacing: .04em;
    text-transform: uppercase;
    border-bottom: 2px solid var(--border);
  }}
  .table-wrap th.num, .table-wrap td.num {{ text-align: right; }}
  .table-wrap tbody td {{
    padding: 10px 14px; border-bottom: 1px solid var(--border);
    vertical-align: top;
  }}
  .table-wrap tbody tr:nth-child(even) td {{ background: #f5faf1; }}
  .table-wrap tbody tr:last-child td {{ border-bottom: none; }}

  code {{ background: #eceae5; padding: 1px 5px; border-radius: 3px; font-size: .9em; }}

  footer {{
    margin-top: 60px; padding-top: 20px;
    border-top: 1px solid var(--border);
    color: var(--muted); font-size: 0.88rem;
  }}
  @media (max-width: 640px) {{
    .container {{ padding: 24px 14px 60px; }}
    h1 {{ font-size: 1.6rem; }}
    .snapshot {{ gap: 16px; }}
    .bar-row {{ grid-template-columns: 100px 1fr 36px; }}
  }}
</style>
</head>
<body>
<aside class="toc" aria-label="Page navigation">
  <div class="toc-label">On this page</div>
  <ul>
    <li><a href="#intro" data-toc-link>Overview</a></li>
    <li><a href="#snapshot" data-toc-link>Snapshot</a></li>
    <li><a href="#sector-function" data-toc-link>Sector × Function</a></li>
    <li><a href="#by-status" data-toc-link>By status</a>
      <ul>
        <li class="sub"><a href="#bucket-thriving" data-toc-link>Thriving</a></li>
        <li class="sub"><a href="#bucket-healthy" data-toc-link>Healthy</a></li>
        <li class="sub"><a href="#bucket-watchlist" data-toc-link>Watchlist</a></li>
        <li class="sub"><a href="#bucket-dormant" data-toc-link>Dormant</a></li>
        <li class="sub"><a href="#bucket-likely-dead" data-toc-link>Likely Dead</a></li>
        <li class="sub"><a href="#bucket-pivoted-absorbed" data-toc-link>Pivoted</a></li>
      </ul>
    </li>
  </ul>
</aside>
<div class="container">
  <h1>AI Startup Survival Tracker</h1>
  <p class="lede">{summary}</p>
  <p class="meta">Refreshed {refreshed}. 7 public signals per company. <a href="METHODOLOGY.md">Methodology</a>. <a href="https://github.com/sridevivr/ai-startup-survival-tracker">Code</a>.</p>
  {banner_html}

  {hero_stats_html}

  <hr class="section-rule"/>
  <section class="intro section-head" id="intro">
    <span class="eyebrow">Overview</span>
    {intro_html}
  </section>

  <hr class="section-rule"/>
  <div class="section-head" id="snapshot">
    <span class="eyebrow">Section 01 · Snapshot</span>
    <h2>Today's snapshot</h2>
  </div>
  <div class="snapshot">
    {donut_svg}
    <div class="legend"><ul>{status_legend}</ul></div>
  </div>

  <hr class="section-rule"/>
  <div class="section-head" id="sector-function">
    <span class="eyebrow">Section 02 · Cross-axis view</span>
    <h2>Sector × Function</h2>
  </div>
  <div class="heatmap-card">
    <p class="caption">What this chart shows: how the cohort concentrates when you cross the vertical a company serves (row) with where it sits in the AI stack (column). Darker cells are more companies. Hover a cell for the exact count.</p>
    {heatmap_svg}
    {heatmap_legend_html}
  </div>

  <hr class="section-rule"/>
  <div class="section-head" id="by-status">
    <span class="eyebrow">Section 03 · By status</span>
    <h2>By status</h2>
  </div>
  {bucket_sections}

  {delta_block}

  <div class="author-card">
    <h4>About this project</h4>
    <p>Built by <a href="https://sridevivr.com">Sridevi Vijayaraghavan</a>. Ex-VMware Technical Program Manager, now building with AI.</p>
    <p class="bio">Read the essay about how this was built on <a href="https://impulsedinertia.substack.com/">Impulsed Inertia</a>, or see more projects at <a href="https://sridevivr.com">sridevivr.com</a>.</p>
  </div>

  <footer>
    <p>Triage tool, not verdict. Every finding should be human-verified before it shapes a decision. Methodology, weights, and limitations documented in <a href="METHODOLOGY.md">METHODOLOGY.md</a>.</p>
  </footer>
</div>

<script>
(function() {{
  // Shared filter logic. Each bucket has two <select> filters; changes update
  // visibility on that bucket's .company cards only.
  function applyFilter(bucketId) {{
    var grid = document.getElementById(bucketId + "-grid");
    if (!grid) return;
    var selects = document.querySelectorAll('select[data-bucket="' + bucketId + '"]');
    var sector = null, fn = null;
    selects.forEach(function(s) {{
      if (s.dataset.role === "sector-filter") sector = s.value;
      if (s.dataset.role === "function-filter") fn = s.value;
    }});
    var cards = grid.querySelectorAll(".company");
    var visible = 0;
    cards.forEach(function(el) {{
      var matchS = !sector || sector === "All" || el.dataset.sector === sector;
      var matchF = !fn || fn === "All" || el.dataset["function"] === fn;
      var hidden = !(matchS && matchF);
      el.classList.toggle("hidden", hidden);
      if (!hidden) visible++;
    }});
    var counter = document.querySelector('.filter-visible-count[data-bucket="' + bucketId + '"]');
    if (counter) counter.textContent = "Showing " + visible + " of " + cards.length;
  }}

  document.querySelectorAll("select[data-bucket]").forEach(function(s) {{
    s.addEventListener("change", function() {{ applyFilter(s.dataset.bucket); }});
  }});
  document.querySelectorAll(".reset-btn").forEach(function(btn) {{
    btn.addEventListener("click", function() {{
      var id = btn.dataset.bucket;
      document.querySelectorAll('select[data-bucket="' + id + '"]').forEach(function(s) {{
        s.value = "All";
      }});
      applyFilter(id);
    }});
  }});

  // Scrollspy: highlight the current section's link in the left-hand TOC
  // as the reader scrolls. Uses IntersectionObserver with a viewport band
  // centered ~40% from the top so the active link feels natural.
  var tocLinks = document.querySelectorAll("[data-toc-link]");
  var targets = [];
  tocLinks.forEach(function(link) {{
    var id = link.getAttribute("href").slice(1);
    var el = document.getElementById(id);
    if (el) targets.push({{id: id, el: el, link: link}});
  }});
  if ("IntersectionObserver" in window && targets.length) {{
    var activeId = null;
    function setActive(id) {{
      if (id === activeId) return;
      activeId = id;
      tocLinks.forEach(function(l) {{
        l.classList.toggle("active", l.getAttribute("href") === "#" + id);
      }});
    }}
    var observer = new IntersectionObserver(function(entries) {{
      // Pick the topmost intersecting entry
      var visible = entries.filter(function(e) {{ return e.isIntersecting; }});
      if (!visible.length) return;
      visible.sort(function(a, b) {{ return a.boundingClientRect.top - b.boundingClientRect.top; }});
      setActive(visible[0].target.id);
    }}, {{ rootMargin: "-20% 0px -60% 0px", threshold: 0 }});
    targets.forEach(function(t) {{ observer.observe(t.el); }});
  }}
}})();
</script>
</body>
</html>
"""


def main() -> None:
    p = argparse.ArgumentParser(description="Build the recruiter-facing publish.html.")
    p.add_argument("--signals", default="output/signals.json")
    p.add_argument("--out", default="output/publish.html")
    p.add_argument("--index", default="index.html",
                   help="Root-level copy for GitHub Pages. Pass empty to skip.")
    p.add_argument("--diffs-dir", default="snapshots/diffs")
    args = p.parse_args()
    build(args.signals, args.out, args.index or None, args.diffs_dir)


if __name__ == "__main__":
    main()
