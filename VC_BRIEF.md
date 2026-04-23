# AI Startup Survival Tracker — April 2026 Brief

*A monthly public-signals scan of the 2023–2025 AI startup cohort. Produced automatically from the open web — homepage uptime, code velocity, hiring pulse, blog cadence, Wayback snapshots, and trusted-source news. AI cross-checked via browser navigation + Google News on a curated core.*

## The one-line finding

**Of 577 AI companies tracked in the 2023+ cohort, two thirds sit in the ambiguous middle — neither thriving nor obviously dead.** Only 26 score as Thriving and only 49 as Likely Dead. The remaining 502 are a distribution problem: 82 Healthy, 11 Dormant, 25 Pivoted, and 384 on the Watchlist — companies with live sites and mixed signal coverage that will take years to resolve into hits, acquihires, or write-offs.

## The cohort in one table

| Status | Count | Share |
|---|---|---|
| Thriving (≥80) | 26 | 4.5% |
| Healthy (65–79) | 82 | 14.2% |
| Watchlist (45–64) | 384 | 66.6% |
| Dormant (25–44) | 11 | 1.9% |
| Likely Dead (0–24 or trusted death headline or curated death marker) | 49 | 8.5% |
| Pivoted / Absorbed (curated acquisition/acquihire marker) | 25 | 4.3% |

Seven of the 577 rows are AI cross-checked — a Claude-in-Chrome session navigated the site and corroborated the story against Google News. The other 570 are classified from automated signals and curated notes only.

## Who's thriving

The foundation-model oligopoly is still clean. Anthropic (88.8), Mistral (94.3), and Cohere (86.2) all score in the upper band on every signal — live sites, Wayback-fresh, aggressive hiring, active GitHub. The Code AI cluster is the second clean cohort: Cursor (100), Magic (92.7), Greptile (70.9, Healthy), Replicate (87.1). Enterprise and media vertical AI fills out the upper bands — Synthesia (80.0) and Runway (86.2) land in Thriving; Glean (76.4) and Luma AI (73.8) in Healthy; Hippocratic AI (73.8) is the rare clean healthcare name. What these categories share: a paying enterprise customer and a workflow the buyer already owns.

## Who's pivoting

Twenty-five rows carry a curated acquisition/acquihire/rebrand marker. The headline pattern — acquihire, not shutdown — holds at scale: Inflection (MSFT, $650M licensing, March 2024), Adept (Amazon reverse-acquihire, June 2024), Character.AI (Google licensing, August 2024), Humane (HP acquisition, February 2025), Codeium (Google DeepMind + Cognition, July 2025). Of the twenty-five, the seven AI cross-checked rows are the cleanest — each one has independent press corroboration recorded in `data/live_verified.json` with source outlets cited.

**What's new at scale**: YC's own directory flags Langfuse as Acquired, which is why it lands in Pivoted / Absorbed despite scoring 76.9 on operational signals — the product is still shipping under new ownership. That's the correct classification: the label captures the corporate event, the score captures ongoing activity. Without curated overrides, the automated signals would have read Langfuse as Healthy and missed the acquisition entirely.

## Who's dying

Forty-eight rows land in Likely Dead. Three different paths get you there:

- **Score-driven** — enough signals below threshold that the raw numeric score falls under 25. Mostly small YC rows with dead sites, no GitHub, no news.
- **Curated death marker** — notes like "shut down," "bankrupt," "defunct." This catches the clear historical deaths: Argo AI, Olive AI, Ghost Autonomy, Forward Health — all AI cross-checked, all corroborated by multiple Tier-1 outlets.
- **YC Inactive + trusted news death signal** — where the automated scraper wouldn't catch the story alone, but an outside source has. The most interesting example in this run is **Interlock**, which scored 64.6 on automated signals (site up, hiring, GitHub) but YC marks it Inactive — label flips to Likely Dead via curated note. Classic zombie-brand case.

**One contested signal worth flagging for readers**: Suno scores 56.4, has a Fortune headline about RIAA copyright lawsuits (flagged as a death signal by the keyword classifier), *and* has a Forbes health-signal headline from the same 180-day window. The trust-gated override weights the Fortune piece and flips the label to Likely Dead. A human reader may reasonably disagree — lawsuits aren't deaths, and Suno is still operating. Treat this as an "investigate, don't conclude" flag, which is the entire point of a triage product.

## Patterns worth pricing in at scale

**Hiring pulse remains the most reliable leading indicator.** Across the twenty-five Pivoted / Absorbed rows, careers-page activity went stale 2–6 months before the acquisition or shutdown was announced. This replicates the finding from the 37-company first pass on a 15× larger sample.

**Category concentration matters.** Code AI and Foundation Models cluster in Thriving. Consumer AI dominates the Pivoted cohort — Character, Inflection, Humane, Rewind are all consumer-facing. Healthcare AI is bimodal: one survivor (Hippocratic), one high-profile casualty (Olive), and a long tail on the Watchlist. AV remains over-represented in the failure cohort relative to its share of the seed list.

**The Watchlist middle is not a failure of the model, it's the honest answer.** For most 2023-era AI startups — which launched 18–30 months ago — the available public signals just aren't decisive yet. Website uptime is near-ubiquitous, GitHub activity is spotty, press coverage is silent. The 384 Watchlist rows are the ones worth monitoring month-over-month for *deltas*, which is where the real alpha sits.

## Three layers, three kinds of confidence

This brief's classifications come from a deliberately tiered system — each layer catching something the layer below missed:

1. **Automated signals, all 577 companies.** Cheap, fast, fuzzy on edges. Can't catch zombie brands (acquihired teams who leave their marketing site live).
2. **Curated notes, ~50 rows.** Human-captured corporate events (acquisitions, shutdowns, pivots) that override automated signals. Catches the stories YC marks in its own directory and a hand-curated set of high-profile exits.
3. **AI cross-checked, 7 rows.** Claude-in-Chrome navigates the company's site, then runs a Google News query against multiple reputable outlets (NYT, Reuters, Bloomberg, TechCrunch, Fortune, The Verge, etc.). Produces narrative-quality truth for the core cases readers will ask about.

The ratio — 577 automated, 50 curated, 7 cross-checked — reflects what's actually scalable. You cannot hand-verify 577 companies. You cannot trust pure automation on complex stories like acquihires. The layered approach is the product.

## Limitations

- **180-day news window.** Historical defining events (e.g. Microsoft's March 2024 Inflection acquihire) fall outside the trusted-news pass and are captured only via curated notes. Readers evaluating a long-tail row with no curated note are working from automated signals alone.
- **Keyword-based news classification.** A trusted outlet publishing "X commented on layoffs" looks identical to "X had layoffs" to the classifier. The trust-gated label override protects against noise from non-Tier-1 outlets; it doesn't protect against ambiguous headlines from trusted ones. Suno above is one such case.
- **Self-reported surface area.** Six of seven signals measure what the company says about itself (its site, blog, GitHub, jobs). Only news reflects the outside world. That's why news is weighted at 15% and gated on trust.
- **Snapshots, not trends.** A single run is a moment. The interesting artifact is the 6-month delta — companies whose score drops 30+ points between monthly runs are the ones worth a phone call.

## What's next

This is still an MVP. The remaining build-out:

1. **Monthly deltas.** A score-change report is the product. "Who dropped 30 points since last month?" is the question this tool is ultimately trying to answer.
2. **Zero-hiring-activity flags.** Derived from the careers-page delta month-over-month — the cheapest early-warning signal in the dataset.
3. **LinkedIn job-count proxy.** LinkedIn itself is hostile to scrapers, but public job-board aggregators offer a workable substitute.
4. **Category-level heatmaps.** Where is the survival rate collapsing? The scale now supports per-category time series.

Methodology, source code, and the full dataset ship alongside this brief. Everything is reproducible from `data/startups.csv` by running `python tracker.py && python tracker_news.py && python build_dashboard.py`.

---

*Data refreshed: see `output/signals.json` for run timestamp. This brief is a triage product, not a judgment — every finding should be human-verified before it shapes a decision.*
