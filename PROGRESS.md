# YC AI Momentum Heatmap — Progress

Track each step. If the session times out, the next session reads this first.

## Plan reference

`/root/.claude/plans/root-claude-uploads-2b3e1fc7-3f20-4a5a-recursive-dahl.md`

## Live artifacts

- **Data heartbeat:** `data/master.csv` — 9 columns × 144 rows (Step 1).
- **Visual heartbeat:** `output/momentum.html` — grows after every step.
- **Findings:** `insights.md` — numbered I-1 through I-N.

## Step status

### Step 1 — Cut list + master CSV + skeleton HTML
- **Status:** ✅ done
- **Artifacts:**
  - `momentum_cohort.py` — cohort filter
  - `momentum_render.py` — HTML builder (extended each step)
  - `data/master.csv` — 144 rows × 9 columns
  - `output/momentum.html` — cohort summary + density heatmap
- **Verified:**
  - 578 → 534 (founded ≥ 2023) → 471 (after cutting 63 dead/pivoted/dormant) → 144 (after cutting 327 with zero positive signals)
  - HTML parses cleanly (25KB)
  - Top cell: Cross-industry × AI Agent = 20 companies
  - Strongest vertical: Finance × AI Agent = 11 companies
- **Next-verify:** user opens `output/momentum.html`, eyeballs the density heatmap, confirms cut feels right. Style tweaks here while it's still simple.

### Step 2 — Scrape homepages + show activity
- **Status:** ⏳ pending
- **What it does:** fetch homepage HTML (and blog) for each of the 144 companies, save plain text. Layer signal-strength indicators into the heatmap.
- **New files expected:** `momentum_scrape.py`, `data/scraped/<slug>.txt` × ~144
- **Next-verify:** scrape coverage ≥85%, page shows per-cell signal richness as a second visual layer.

### Step 3 — Funding column + funding view
- **Status:** ⏳ pending
- **What it does:** fill the `funding` column in `master.csv` via homepage/blog regex + YC Algolia `stage` + news.json mining. Add view toggle to page.
- **Next-verify:** does the funding view tell a different story than density?

### Step 4 — Sub-sector for Cross-industry rows + mini-grid
- **Status:** ⏳ pending
- **What it does:** classify the ~65 Cross-industry rows into 6–8 sub-sector buckets. Add "Inside Cross-industry" mini-grid below the main one.
- **Next-verify:** does anything that was hiding inside Cross-industry surface?

### Step 5 — Insights up top + featured cells with problem cards
- **Status:** ⏳ pending
- **What it does:** look at the master CSV four ways (density / activity / funding / recency). Featured cells get problem-theme cards. 5 punchy findings pulled into a TL;DR at the top.
- **Next-verify:** can a stranger find the hot cell + name a company in it in 90 seconds?

### Step 6 — Polish + commit
- **Status:** ⏳ pending
- **What it does:** hand-edit `insights.md` prose, sync TL;DR, commit + push to `claude/adoring-gates-8qY6t`.
