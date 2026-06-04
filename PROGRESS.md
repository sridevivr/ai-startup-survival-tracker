# YC AI Momentum Heatmap — Progress

Track each step. If the session times out, the next session reads this first.

## Plan reference

`/root/.claude/plans/root-claude-uploads-2b3e1fc7-3f20-4a5a-recursive-dahl.md`

## Live artifacts

- **Data heartbeat:** `data/master.csv` — 10 cols × 144 rows. Grows column by column.
- **Visual heartbeat:** `output/momentum.html` — magazine-spread layout. Grows after every step.
- **Findings:** `insights.md` — numbered I-1 through I-N. Editorial spine for the page TL;DR.

## Step status

### Step 1 — Cut list + master CSV + skeleton HTML ✅ done
**Commits:** `1c978e2`, `990d710`, `4298e8b`, `4a1c2f1`
- `momentum_cohort.py`, `momentum_render.py`, `data/master.csv` (144 rows × 9 cols), `output/momentum.html`
- Final visual decisions: magazine-spread, Fraunces display serif, Geist body, warm off-white (#faf7f2), terracotta accent (#C24A2C), hand-drawn line icons per functionality. Vocabulary primer (8 cards) opens before the data.
- Cut: 578 → 534 (founded ≥ 2023) → 471 (–63 dead/pivoted/dormant) → 144 (–327 zero positive signals)

### Step 2 — Activity score (data only, no visible view) ✅ done
**Commits:** `2e86dfc`, `231e5fb`
- `momentum_activity.py` computes a per-company two-layer momentum score (alive baseline 0.30 + boost from news/freshness/hiring/blog/github), reuses component scorers from `scoring.py`.
- Added `activity_score` column to `data/master.csv` (now 10 cols).
- Distribution: 13 light (35–54), 99 active (55–74), 32 buzzing (75–100).
- **User feedback: Activity view dropped from the page.** A numeric score is hard to read at a glance. The heatmap reverted to a single Density view. The score stays in the CSV as a backend filter signal but isn't rendered.
- `momentum_scrape.py` was written but **all 144 fetches returned HTTP 403** — the environment network policy blocks outbound HTTPS. WebFetch also blocked. The scrape file is on disk but unused.

### Step 4 — Cross-industry sub-sector decomposition ⏳ NEXT
**Why now (before Step 3):** user prioritized understanding what "Cross-industry" means (65 of 144 = 45% of the cohort).
**Approach (locked in):** B2 = Anthropic Haiku via `scripts/classify_with_llm.py`. No scraping required — use the existing `tagline` column in `data/master.csv` as input text.
**Prerequisites:**
- `ANTHROPIC_API_KEY` must be set in the env. **The user added it to environment config, but the previous session was started before that and couldn't see it. A fresh session is required.** Verify with `echo $ANTHROPIC_API_KEY`.
- `anthropic` Python SDK is already installed via `pip install anthropic` (PyPI is reachable, only arbitrary HTTPS is blocked).
**Tasks:**
1. Verify `ANTHROPIC_API_KEY` is set in this fresh session.
2. Write `momentum_subsector.py`:
   - Read `data/master.csv`, filter to the 65 Cross-industry rows
   - For each, call Haiku with: tagline + functionality → classify into a fixed 6–8 sub-sector taxonomy (Horizontal Dev Tools, Sales & Marketing AI, Foundation Model Lab, Robotics / Embodied, Data & ML Tooling, Productivity & Workflow, Vertical AI Catch-All, Other / Unclassified)
   - Reuse `scripts/classify_with_llm.py` patterns (batched, JSON output, resumable)
   - Write the result back to `data/master.csv` `sub-sector` column
   - Save a side-file `data/subsector.json` with reasoning per company (audit trail)
3. Add "Inside Cross-industry" mini-grid to `momentum_render.py` — sub-sector × functionality, below the main heatmap.
4. Update `insights.md` with finding I-2 describing what Cross-industry actually means.
5. Commit + push.
**Expected cost:** under $0.05 (65 short taglines, batched into ~4–5 Haiku calls).

### Step 3 — Funding column ⏳ deferred
Originally planned before sub-sector but bumped. Without homepage scrape, funding coverage will be lower (~25%). Sources: `output/news.json` regex + YC Algolia `stage` field (if reachable via Algolia's allowlisted endpoint — needs testing).

### Step 5 — Insights up top + featured cells with problem cards ⏳ pending
### Step 6 — Polish + commit ⏳ pending

## Environment notes (for the fresh session)
- Branch: `claude/adoring-gates-8qY6t` — keep working here.
- Repo: `sridevivr/ai-startup-survival-tracker`.
- Network policy: outbound HTTPS to arbitrary domains is blocked (proxy returns 403). PyPI is reachable. Anthropic API is reachable.
- Scraping is OUT (network blocked). Use on-disk data + LLM only.
- Files to read first: this file, then `insights.md`, then `momentum_render.py` and `data/master.csv` to ground yourself.
