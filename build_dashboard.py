"""Regenerate output/dashboard.html from output/signals.json.

Until now dashboard.html had the company DATA hard-coded inline, which was
fine for the 37-company hand-curated seed but wrong the moment seeding
became reproducible. This script rebuilds the HTML from whatever the
scoring step most recently wrote to signals.json, so the loop is:

    seeding/*  →  data/startups.csv  →  tracker.py  →  scoring.py
                 →  output/signals.{csv,json}  →  build_dashboard.py
                                                →  output/dashboard.html

## Why the template is inlined here

The HTML template (CSS + JS) lives as a Python multiline string in this
file rather than as a separate .html file with a placeholder. Two reasons:

1. One less file to keep in sync. Changing the JS and forgetting to
   change the generator is a common bug in split-template setups.
2. The generator is now the single source of truth for the dashboard's
   shape — if you add a new signal column, you change one file.

## What changed from the original inline dashboard

- `.badge.Not` CSS class added for the new "Not Yet Enriched" status
  (muted gray — "we haven't looked yet" is a distinct state from any of
  the scored statuses and should read as neutral, not as a failure).
- Summary-card order now includes "Not Yet Enriched" and "Pivoted /
  Absorbed" explicitly so the card ordering is stable across refreshes.
- Header subtitle is templated: "<N> companies" is computed from the
  data, not hard-coded.
- The news-verified count in the header is also computed (counts rows
  with at least one note starting with "VERIFIED").

Run:
    python build_dashboard.py
    # or with explicit paths:
    python build_dashboard.py --in output/signals.json --out output/dashboard.html
"""
from __future__ import annotations

import argparse
import json
import os
import sys


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>AI Startup Survival Tracker</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root {{ --bg:#0b0d10; --panel:#141820; --panel2:#1a1f29; --fg:#e6e9ef; --muted:#8a93a6; --accent:#7aa2f7; --green:#9ece6a; --yellow:#e0af68; --red:#f7768e; --blue:#7dcfff; --border:#2a303c; }}
*{{box-sizing:border-box}}
body{{margin:0;font:14px/1.55 -apple-system,BlinkMacSystemFont,"SF Pro Text","Inter",system-ui,sans-serif;background:var(--bg);color:var(--fg)}}
header{{padding:28px 32px 22px;border-bottom:1px solid var(--border);background:linear-gradient(180deg,#0f1318,var(--bg))}}
h1{{margin:0 0 6px;font-size:22px;font-weight:600;letter-spacing:-.01em}}
header p{{margin:0;color:var(--muted);font-size:13px}}
.meta{{margin-top:14px;color:var(--muted);font-size:12px}}
.container{{padding:24px 32px 60px;max-width:1400px}}
.summary{{display:flex;gap:12px;margin-bottom:22px;flex-wrap:wrap}}
.card{{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:14px 18px;min-width:150px}}
.card .n{{font-size:24px;font-weight:600;letter-spacing:-.02em}}
.card .l{{color:var(--muted);font-size:12px;margin-top:2px;text-transform:uppercase;letter-spacing:.06em}}
.controls{{display:flex;gap:12px;margin-bottom:14px;flex-wrap:wrap;align-items:center}}
input[type=search],select{{background:var(--panel);border:1px solid var(--border);color:var(--fg);padding:8px 12px;border-radius:8px;font:inherit;min-width:240px}}
input[type=search]:focus,select:focus{{outline:none;border-color:var(--accent)}}
table{{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--border);border-radius:10px;overflow:hidden}}
th,td{{padding:10px 14px;text-align:left;border-bottom:1px solid var(--border)}}
th{{background:var(--panel2);color:var(--muted);font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.07em;cursor:pointer;user-select:none;white-space:nowrap}}
th:hover{{color:var(--fg)}}
tbody tr:hover{{background:#171c25}}
tbody tr.expanded{{background:#171c25}}
tbody tr:last-child td{{border-bottom:0}}
.name{{font-weight:600;letter-spacing:-.01em}}
.name a{{color:var(--fg);text-decoration:none}}
.name a:hover{{text-decoration:underline;color:var(--accent)}}
.category{{color:var(--muted);font-size:12px}}
.score{{display:inline-block;min-width:44px;padding:2px 8px;border-radius:999px;font-weight:600;font-size:12px;text-align:center;background:#20263049}}
.score-bar-wrap{{width:80px;height:5px;background:#232936;border-radius:3px;overflow:hidden;margin-top:3px}}
.score-bar{{height:100%;border-radius:3px}}
.badge{{display:inline-block;padding:3px 9px;font-size:11px;font-weight:500;border-radius:999px;border:1px solid transparent;white-space:nowrap}}
.badge.Thriving{{background:#1f3222;border-color:#2f4d33;color:var(--green)}}
.badge.Healthy{{background:#203024;border-color:#2e4733;color:var(--green)}}
.badge.Watchlist{{background:#33281a;border-color:#50401f;color:var(--yellow)}}
.badge.Dormant{{background:#2a2a1b;border-color:#45441f;color:var(--yellow)}}
.badge.Likely{{background:#32222a;border-color:#53303d;color:var(--red)}}
.badge.Pivoted{{background:#1e2a36;border-color:#2b3f52;color:var(--blue)}}
.badge.Not{{background:#1c1f27;border-color:#353a48;color:var(--muted)}}
.source-tag{{display:inline-block;margin-left:6px;padding:1px 6px;font-size:10px;font-weight:500;border-radius:4px;background:#1c1f27;color:var(--muted);border:1px solid #2a303c;text-transform:uppercase;letter-spacing:.05em}}
.signals{{color:var(--muted);font-size:12px}}
.signals strong{{color:var(--fg);font-weight:500}}
.expand-row td{{background:#10141b;padding:14px 22px 18px;border-bottom:1px solid var(--border)}}
.expand-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px 22px}}
.expand-grid dt{{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:2px}}
.expand-grid dd{{margin:0 0 8px;font-size:13px}}
.notes{{margin-top:12px;padding-top:12px;border-top:1px dashed var(--border);color:var(--muted);font-size:12px;line-height:1.6}}
.notes .note-item{{margin:5px 0;padding-left:10px;border-left:2px solid #2a303c}}
.notes .verified-note{{border-left-color:var(--accent);color:#d0d5e0}}
.verified-badge{{color:var(--accent);font-size:11px;margin-left:6px;font-weight:500}}
footer{{margin-top:40px;padding-top:22px;border-top:1px solid var(--border);color:var(--muted);font-size:12px}}
.caret{{display:inline-block;width:0;height:0;margin-right:6px;border-left:4px solid transparent;border-right:4px solid transparent;border-top:5px solid var(--muted);transform:rotate(-90deg);transition:transform .15s}}
tr.expanded .caret{{transform:rotate(0deg)}}
</style>
</head>
<body>
<header>
  <h1>AI Startup Survival Tracker</h1>
  <p>Public-signals snapshot of the 2023–2025 AI startup cohort. {company_count} companies, six signals per company, single triage score.</p>
  <div class="meta">Refreshed <span id="meta-date"></span> · signals: website uptime · Wayback freshness · blog cadence · GitHub velocity · hiring pulse · curated overrides · <strong style="color:var(--accent)">{verified_count} entries AI cross-checked (browser navigation + Google News)</strong> · seed: <code>{seed_summary}</code></div>
</header>

<div class="container">
  <div class="summary" id="summary"></div>
  <div class="controls">
    <input type="search" id="search" placeholder="Filter by name or category…">
    <select id="statusFilter"><option value="">All statuses</option></select>
    <select id="categoryFilter"><option value="">All categories</option></select>
    <span class="meta" id="visibleCount" style="margin-left:auto"></span>
  </div>
  <table id="t">
    <thead><tr>
      <th data-sort="name">Company</th>
      <th data-sort="category">Category</th>
      <th data-sort="score">Score</th>
      <th data-sort="status">Status</th>
      <th>Signals</th>
    </tr></thead>
    <tbody></tbody>
  </table>

  <footer>
    <strong>Score = triage, not verdict.</strong> A low score is a reason to investigate, not a conclusion. Entries marked <span class="verified-badge">✓ AI cross-checked</span> were checked two independent ways by a Claude-in-Chrome session: direct browser navigation to the company's site AND a Google News query against multiple reputable outlets. Seed is drawn from multiple public sources (see <code>seeding/SEEDING.md</code>); statuses marked <span class="badge Not">Not Yet Enriched</span> are seed-only entries awaiting a live tracker run. Refresh via <code>python tracker.py &amp;&amp; python build_dashboard.py</code>. See <code>METHODOLOGY.md</code> for weight rationale and known limitations.
  </footer>
</div>

<script>
const DATA = {data_json};
document.getElementById("meta-date").textContent = DATA[0]?.checked_at?.slice(0,10) || '—';

function scoreColor(s) {{
  if (s == null) return "#55606f";
  if (s >= 80) return "#9ece6a";
  if (s >= 65) return "#b8c76a";
  if (s >= 45) return "#e0af68";
  if (s >= 25) return "#ff9e64";
  return "#f7768e";
}}
function badgeClass(status) {{
  const key = (status || "").split(/[ /]/)[0];
  return "badge " + key;
}}
function fmt(v, suffix="") {{ return v == null ? '<span style="color:#55606f">—</span>' : v + suffix; }}
function isVerified(d) {{ return (d.notes || []).some(n => /^VERIFIED/.test(n)); }}

// Summary cards — order chosen so the "alive" states read left-to-right
// before the "dead / absorbed / unknown" states.
const counts = {{}};
DATA.forEach(d => {{ counts[d.status] = (counts[d.status] || 0) + 1; }});
const order = ["Thriving", "Healthy", "Watchlist", "Dormant", "Likely Dead", "Pivoted / Absorbed", "Not Yet Enriched"];
document.getElementById("summary").innerHTML =
  `<div class="card"><div class="n">${{DATA.length}}</div><div class="l">Tracked</div></div>` +
  order.filter(s => counts[s]).map(s => `<div class="card"><div class="n">${{counts[s]}}</div><div class="l">${{s}}</div></div>`).join("");

// Filters
const statusFilter = document.getElementById("statusFilter");
Object.keys(counts).sort().forEach(s => {{
  const o = document.createElement("option"); o.value = s; o.textContent = s; statusFilter.appendChild(o);
}});
const categoryFilter = document.getElementById("categoryFilter");
[...new Set(DATA.map(d => d.category))].sort().forEach(c => {{
  if (!c) return;
  const o = document.createElement("option"); o.value = c; o.textContent = c; categoryFilter.appendChild(o);
}});

const tbody = document.querySelector("#t tbody");
let sortKey = "survival_score", sortDir = -1;
let filter = "", statusSel = "", categorySel = "";

function renderNotes(notes) {{
  if (!notes || !notes.length) return "";
  const items = notes.map(n => {{
    const verified = /^VERIFIED/.test(n);
    const cls = verified ? "note-item verified-note" : "note-item";
    return `<div class="${{cls}}">${{n.replace(/</g, "&lt;")}}</div>`;
  }}).join("");
  return `<div class="notes"><strong>Notes &amp; sources:</strong>${{items}}</div>`;
}}

function render() {{
  const q = filter.toLowerCase();
  const rows = DATA.filter(d =>
    (!q || d.name.toLowerCase().includes(q) || (d.category || "").toLowerCase().includes(q)) &&
    (!statusSel || d.status === statusSel) &&
    (!categorySel || d.category === categorySel)
  ).sort((a, b) => {{
    const av = a[sortKey], bv = b[sortKey];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (av < bv) return -1 * sortDir;
    if (av > bv) return 1 * sortDir;
    return 0;
  }});
  tbody.innerHTML = rows.map((d, i) => {{
    const verified = isVerified(d) ? '<span class="verified-badge">✓ AI cross-checked</span>' : '';
    const sc = scoreColor(d.survival_score);
    const pct = d.survival_score == null ? 0 : d.survival_score;
    const careers = d.careers_page_found == null ? '—' : (d.careers_page_found ? (d.jobs_detected || 0) + ' jobs' : 'none');
    return `
      <tr data-idx="${{i}}">
        <td><div class="name"><a href="${{d.website || '#'}}" target="_blank" rel="noopener">${{d.name}}</a>${{verified}}</div><div class="category">Founded ${{d.founded || '—'}}</div></td>
        <td><span class="category">${{d.category || '—'}}</span></td>
        <td>
          <span class="score" style="color:${{sc}}">${{d.survival_score == null ? '—' : d.survival_score.toFixed(1)}}</span>
          <div class="score-bar-wrap"><div class="score-bar" style="width:${{pct}}%;background:${{sc}}"></div></div>
        </td>
        <td><span class="${{badgeClass(d.status)}}">${{d.status || '—'}}</span></td>
        <td class="signals">
          <strong>HTTP</strong> ${{d.http_status == null ? '—' : d.http_status}} ·
          <strong>Wayback</strong> ${{d.wayback_last_snapshot_days == null ? '—' : d.wayback_last_snapshot_days + 'd'}} ·
          <strong>Blog</strong> ${{d.feed_last_post_days == null ? '—' : d.feed_last_post_days + 'd'}} ·
          <strong>GH</strong> ${{d.github_commits_90d == null ? '—' : d.github_commits_90d}} ·
          <strong>Hiring</strong> ${{careers}}
        </td>
      </tr>
      <tr class="expand-row" style="display:none" data-expand="${{i}}"><td colspan="5">
        <dl class="expand-grid">
          <div><dt>Survival score</dt><dd>${{d.survival_score ?? '—'}} / 100</dd></div>
          <div><dt>Signal coverage</dt><dd>${{d.signal_coverage == null ? '—' : Math.round(d.signal_coverage * 100) + '%'}}</dd></div>
          <div><dt>HTTP status</dt><dd>${{fmt(d.http_status)}}</dd></div>
          <div><dt>Wayback snapshot</dt><dd>${{fmt(d.wayback_last_snapshot_days, ' days ago')}}</dd></div>
          <div><dt>Last blog post</dt><dd>${{fmt(d.feed_last_post_days, ' days ago')}}</dd></div>
          <div><dt>GitHub commits (90d)</dt><dd>${{fmt(d.github_commits_90d)}}</dd></div>
          <div><dt>Careers page</dt><dd>${{d.careers_page_found == null ? '—' : (d.careers_page_found ? 'found' : 'not found')}}</dd></div>
          <div><dt>Job links detected</dt><dd>${{fmt(d.jobs_detected)}}</dd></div>
        </dl>
        ${{renderNotes(d.notes)}}
      </td></tr>
    `;
  }}).join("");
  document.getElementById("visibleCount").textContent = `${{rows.length}} of ${{DATA.length}} shown`;
}}

document.querySelectorAll("th[data-sort]").forEach(th => {{
  th.addEventListener("click", () => {{
    const k = th.dataset.sort;
    const keyMap = {{ name: "name", category: "category", score: "survival_score", status: "status" }};
    const newKey = keyMap[k];
    if (sortKey === newKey) sortDir *= -1; else {{ sortKey = newKey; sortDir = (newKey === "survival_score") ? -1 : 1; }}
    render();
  }});
}});
document.getElementById("search").addEventListener("input", e => {{ filter = e.target.value; render(); }});
document.getElementById("statusFilter").addEventListener("change", e => {{ statusSel = e.target.value; render(); }});
document.getElementById("categoryFilter").addEventListener("change", e => {{ categorySel = e.target.value; render(); }});

tbody.addEventListener("click", e => {{
  const row = e.target.closest("tr[data-idx]");
  if (!row || e.target.tagName === "A") return;
  const idx = row.dataset.idx;
  const expand = tbody.querySelector(`tr[data-expand="${{idx}}"]`);
  const open = expand.style.display !== "none";
  expand.style.display = open ? "none" : "";
  row.classList.toggle("expanded", !open);
}});

render();
</script>
</body>
</html>
"""


def seed_summary_from_csv(startups_csv: str) -> str:
    """Build a compact one-liner about the seed sources.

    Reads the `sources` column from data/startups.csv and counts each
    source combination. Kept deliberately terse — the full breakdown
    lives in SEEDING.md; the header just needs one phrase.
    """
    try:
        import csv
        from collections import Counter
        with open(startups_csv, encoding="utf-8") as f:
            r = csv.DictReader(f)
            counts: Counter = Counter()
            for row in r:
                sources = (row.get("sources") or "").split("|")
                for s in sources:
                    if s:
                        counts[s] += 1
        parts = [f"{v} {k}" for k, v in counts.most_common()]
        return ", ".join(parts) if parts else "curated"
    except FileNotFoundError:
        return "curated"


def build(signals_path: str, out_path: str, startups_csv: str) -> int:
    with open(signals_path, encoding="utf-8") as f:
        data = json.load(f)

    verified_count = sum(
        1 for d in data
        if any((n or "").startswith("VERIFIED") for n in (d.get("notes") or []))
    )

    # Inlined JSON: use compact separators for a smaller HTML but keep
    # it parseable. ensure_ascii=False keeps accents/etc. readable.
    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    html = TEMPLATE.format(
        company_count=len(data),
        verified_count=verified_count,
        seed_summary=seed_summary_from_csv(startups_csv),
        data_json=data_json,
    )

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Wrote {out_path}", file=sys.stderr)
    print(f"  companies: {len(data)}", file=sys.stderr)
    print(f"  verified:  {verified_count}", file=sys.stderr)
    # Status counts — mirrors what the dashboard will show
    from collections import Counter
    by_status = Counter(d.get("status") for d in data)
    for status, n in by_status.most_common():
        print(f"  {status:<20} {n}", file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="inp", default="output/signals.json",
                    help="Path to signals.json (default: output/signals.json)")
    ap.add_argument("--out", default="output/dashboard.html",
                    help="Where to write the dashboard (default: output/dashboard.html)")
    ap.add_argument("--startups", default="data/startups.csv",
                    help="Path to startups.csv for seed-source header tag")
    args = ap.parse_args()

    # Resolve relative paths against the script's directory so the
    # script works regardless of where it's invoked from.
    here = os.path.dirname(os.path.abspath(__file__))
    def R(p):
        return p if os.path.isabs(p) else os.path.join(here, p)

    return build(R(args.inp), R(args.out), R(args.startups))


if __name__ == "__main__":
    raise SystemExit(main())
