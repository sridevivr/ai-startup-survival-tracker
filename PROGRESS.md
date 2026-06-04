# YC AI Momentum Heatmap — Progress

Track each step. If the session times out, the next session reads this first.

## Plan reference

`/root/.claude/plans/root-claude-uploads-2b3e1fc7-3f20-4a5a-recursive-dahl.md`

## Live artifacts

- **Data heartbeat:** `data/master.csv` — 9 columns × 144 rows. Grows column by column.
- **Visual heartbeat:** `output/momentum.html` — magazine-spread layout. Grows after every step.
- **Findings:** `insights.md` — numbered I-1 through I-N. Editorial spine for the page TL;DR.

## Step status

### Step 1 — Cut list + master CSV + skeleton HTML ✅ done
**Commits:** `1c978e2` (cohort + skeleton), `990d710` (visual redesign), `4298e8b` (magazine spread + vocabulary primer)
- `momentum_cohort.py` — filters startups.csv → master.csv
- `momentum_render.py` — magazine-spread HTML builder (extended each step)
- `data/master.csv` — 144 rows × 9 columns
- `output/momentum.html` — masthead, hero w/ At-a-Glance sidebar, vocabulary primer (8 functionality cards + hand-drawn icons), two-column cohort math, density heatmap
- **Visual decisions locked in:**
  - Warm off-white background (#faf7f2), Fraunces display serif, Geist body, Geist Mono labels, single terracotta accent (#C24A2C)
  - Hand-drawn line icons per functionality (terracotta stroke)
  - Open with vocabulary primer BEFORE the data — readers learn what the 8 functions mean first
- **Verified:** 578 → 534 (founded ≥ 2023) → 471 (–63 dead/pivoted/dormant) → 144 (–327 zero positive signals). HTML parses cleanly.

### Step 2 — Scrape homepages + show activity ⏳ next
**What it does:**
- Fetches each company's homepage (and blog if available), saves plain text → `data/scraped/<slug>.txt`. Plumbing for Step 3 (funding regex) and Step 4 (sub-sector classification).
- Layers a **signal-strength view** onto the heatmap so each tile shows not just *how many*, but *how active* the companies in that cell are.
- Likely path: page gets a small toggle (Density / Activity) and a second heatmap rendering. Activity = mean of (news 180d, fresh site, hiring, fresh blog, github commits) normalized 0–1 per cell.
**New files expected:** `momentum_scrape.py`, `data/scraped/<slug>.txt` × ~144
**Next-verify:** scrape coverage ≥ 85%. Page shows per-cell activity intensity. Do different cells lead by activity vs density?

### Step 3 — Funding column + funding view ⏳ pending
Fills the `funding` column from scraped text + YC Algolia `stage` + news.json. Adds a third view (Funding) to the heatmap toggle.

### Step 4 — Sub-sector for Cross-industry rows + mini-grid ⏳ pending
Classifies the ~65 Cross-industry rows into 6–8 buckets. Adds an "Inside Cross-industry" mini-grid.

### Step 5 — Insights up top + featured cells with problem cards ⏳ pending
Pulls 5 punchy findings into a TL;DR at top of page. Featured cells get problem-theme cards.

### Step 6 — Polish + commit ⏳ pending
Hand-edit `insights.md` prose, sync TL;DR, final commit.
