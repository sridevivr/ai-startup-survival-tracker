# Methodology: AI Startup Survival Score

## What we measure

We pull seven public signals per tracked company and blend them into a single 0–100 survival score. Every signal is collected from a source a VC analyst could check by hand in a browser — nothing proprietary, nothing paywalled, nothing requiring OAuth.

| Signal | Source | What it tells us | Weight |
|---|---|---|---|
| Website uptime | HTTP GET of homepage | Does the company still exist online? | 20% |
| Homepage freshness | Wayback Machine `available` API | When did the internet last notice this site? | 10% |
| Blog freshness | RSS/Atom auto-discovery + common paths | Is the team still publishing? | 10% |
| Code velocity | GitHub public API (org-level commits, 90 days) | Is engineering still shipping? | 15% |
| Hiring pulse | Careers page detection + job-link counting | Is the company still growing headcount? | 20% |
| Trusted news | Google News RSS, filtered to allowlisted sources | What does reputable press say in the last 180 days? | 15% |
| Manual override | Curated `notes` column + news verification | Captures acquihires, shutdowns, pivots | 10% |

Every override claim (shutdown, pivot, acquihire) is backed by a Google News cross-check with citations stored in `data/live_verified.json`. News signal hits are recorded with source domain and trust flag, so the dashboard can explain *why* a company got the label it did.

## Signal design — six self-reported, one external

The first six signals are all *self-reported* in the loose sense — they measure the company's own surface area (its site, its blog, its repo, its job page). That makes them cheap but one-sided: a company that's quietly winding down can still have a live site, a stale blog, and a careers page with zero jobs for months.

News is the one signal that reflects the outside world's view. That's why it's weighted as heavily as GitHub velocity (15%) — but it's also why it has the most defences built around it (see the trust model section below).

## How the score is computed

Each component returns a value in `[0, 1]`. Missing signals are dropped from the weighted average rather than treated as zero — a company that doesn't publish a blog isn't penalised for something it never had. The denominator scales with the resolved signals, and a separate `signal_coverage` field records how many of the seven resolved for each row (from 0.0 to 1.0).

The status label is derived from the score with four overrides, in priority order:

1. **Death marker in notes** (`shut down`, `ceased`, `defunct`, `bankrupt`, `liquidated`) → **Likely Dead**.
2. **Pivot marker in notes** (`pivot`, `acquihire`, `acquired`, `licensing deal`, `acquisition`, `rebranded`) → **Pivoted / Absorbed**. This matters because acquihired teams often leave their sites up for months — the website-uptime signal would otherwise read them as healthy.
3. **Trusted news death signal** — a death-keyword headline in the last 180 days from an allowlisted source → **Likely Dead**. An *untrusted* death headline lowers the numeric score but does not flip the label.
4. **Coverage = 0** → **Not Yet Enriched**. Prevents rows with no resolved signals from defaulting to "Likely Dead" purely because the raw score is 0.

| Score | Label |
|---|---|
| 80–100 | Thriving |
| 65–79 | Healthy |
| 45–64 | Watchlist |
| 25–44 | Dormant |
| 0–24 | Likely Dead |

## Why these weights

Website uptime and hiring are the two highest raw signals (20% each). Website uptime is the cheapest and most reliable ground truth — a `DNS NXDOMAIN` or persistent 5xx is near-conclusive. Hiring is the best leading indicator of operator intent: companies that are quietly winding down stop posting jobs weeks or months before they announce anything.

GitHub velocity and trusted news both sit at 15%. Code activity catches companies that have gone dark in marketing but are still shipping (or the reverse). News catches pivots and funding events that self-reported signals can't see.

Blog freshness and Wayback freshness are weighted lower (10% each) because they're noisy — plenty of healthy companies go quiet on both. The Wayback Machine snapshot is a secondary freshness check that catches cases where the homepage hasn't changed but someone out there has noticed the site recently.

The 10% manual-override slot exists because some deaths are *announced* rather than observed. When the *Wall Street Journal* reports an acquihire, the most reliable source is the *WSJ* article, not our scraper.

## Seed sources

The 577-company dataset is assembled from three sources, merged and deduplicated by normalised website (with normalised-name fallback):

- **YC Work at a Startup** (`seeding/ycombinator.py`) — AI-tagged companies from 2023+ batches. YC exposes an `algolia_search_key` in its public page source that we reuse to page through the directory. Inactive and Acquired statuses are translated into tracker-compatible notes so the scoring path picks them up automatically.
- **Product Hunt** (`seeding/producthunt.py`) — AI-topic launches. Defaults to public mode (parses the inline Apollo cache out of topic pages — no auth). Authenticated GraphQL mode is available via `PH_TOKEN` and is the only way to resolve product websites, since PH hides them behind a tracking redirect in public HTML. PH rows are date-filtered to the 2023+ launch window; undated rows (typically long-running brands like Figma/Slack that get AI tags) are dropped.
- **Curated** (`data/startups.csv`) — 37 hand-picked rows covering the widely-covered core cohort (foundation model majors, enterprise verticals, high-profile acquihires). Seven of these carry an additional AI cross-check layer in `data/live_verified.json` — a Claude-in-Chrome session that navigated to the site and corroborated the story against Google News. This curated list is the highest-priority source in the merger, so manual corrections survive seed refreshes.

## Trust model for news

News is the only signal that isn't self-reported, which makes it both the most valuable and the most attackable. Three layers of defence:

### Layer 1 — Trusted source allowlist (default on)

Only headlines from ~33 vetted domains count toward the news signal. The list covers four buckets:

- **Startup / VC press**: TechCrunch, The Information, Axios, Forbes, VentureBeat, Business Insider, Crunchbase News, PitchBook, Sifted, Semafor
- **Business / financial**: Bloomberg, Reuters, WSJ, FT, NYT, Washington Post, The Economist, CNBC, Fortune, Fast Company, MarketWatch
- **Tech press**: The Verge, Wired, Ars Technica, The Register, Engadget, The Guardian, The Atlantic, MIT Technology Review
- **Primary sources**: sec.gov, AP News, PR Newswire, Business Wire

Extra trusted domains can be added via `my_trusted.txt` (one domain per line). Trusted-only is the default; pass `--allow-untrusted` to include the long tail.

### Layer 2 — Title-based on-topic filter

Google News RSS returns articles where the query string appears anywhere in the article body, not necessarily about the subject. That produced noisy false positives — an xAI article leaking into an Inflection AI query, a Stability AI piece attributed to Inflection, etc.

The filter requires at least one distinctive token from the company name (lowercase, length ≥ 3, with generic tokens like "ai", "inc", "labs", "tech", "co", "corp", "systems" stripped) to appear as a whole word in the article title. This is a coarse filter — it won't catch every name collision — but it eliminates the clearest failure mode where the company isn't mentioned in the headline at all.

### Layer 3 — Trust-gated label override

A death headline can flip a company's label to **Likely Dead**, but only if the source is trusted. Untrusted death signals still lower the numeric score through the news component, but they cannot force the label. This keeps clickbait outlets from mislabeling long-tail companies that no Tier-1 outlet has actually covered.

In practice the layering works as: curated notes (ground truth) > scoring aggregate > news (single data source). For the 37 curated companies, news noise is cosmetic. For the 540 long-tail YC + Product Hunt rows where curation isn't feasible, the trust model is what keeps labels defensible.

## News classification rubric

`_news_score` maps the news fields (from `tracker_news.py`) into `[0, 1]`:

- **Trusted death signal in last 180 days** → 0.0
- **Trusted health signal** (funding round, IPO, product launch) in last 180 days → 1.0
- **No news in last 180 days** → 0.2 (weak negative — silent press isn't death, but isn't health either)
- **Recent coverage, neutral sentiment** → scaled 0.25 → 0.7 by how recent

No news fields at all → the component returns `None` and is dropped from the weighted average, keeping coverage honest.

## What we do *not* claim

- **This is triage, not verdict.** A low score means "check on this company," not "this company is dead." Every interesting finding should be human-verified.
- **Absence of signal ≠ death.** Midjourney scores well here because its site is up and Wayback is watching it, even though it publishes no blog, no careers page, and no public GitHub activity. Low-on-all-signals companies might just be private by design.
- **Snapshots, not trends.** A single run is a moment. The interesting artifact is the 6-month delta — companies whose score drops 30+ points between monthly runs are the ones worth a phone call.
- **180-day news window.** Historical defining events (for example Microsoft's March 2024 Inflection acquihire) fall outside the window and are not caught by the news pass. Those should be captured in curated notes, which override everything.

## Limitations

- **Seeding relies on YC's self-tagging.** The YC adapter filters by the "Artificial Intelligence" tag, so AI-adjacent companies that don't carry that tag in YC's directory are excluded — even when they plausibly use ML under the hood. HockeyStack (Summer 2023) is a concrete example: tagged SaaS / B2B / Analytics / Sales / Marketing but not AI, despite a product that clearly depends on account-scoring and predictive segmentation. This biases the automated seed toward companies that chose to *position* as AI, which is a different population than "companies using AI." The curated `data/startups.csv` layer is the escape hatch for names the YC filter misses — false negatives can be added manually and will survive future seed refreshes because curated rows are the merger's highest-priority source.
- Twitter/X activity is omitted because the public, unauthenticated API was effectively shut down in 2023.
- LinkedIn job counts would be the gold standard for hiring pulse; careers-page scraping is a proxy because LinkedIn blocks scrapers.
- App Store / Play Store review velocity is planned, not yet implemented.
- Crunchbase funding freshness would be valuable but is gated behind a paid API.
- Google News RSS surfaces headlines that *mention* the query string; even after the title-on-topic filter, some name collisions slip through (e.g. a textile-materials "Adept" versus Adept AI). Low-volume, ambiguous signals are why news is capped at 15% rather than weighted higher.
- The curated notes list is only as good as the human maintaining it. Refresh monthly alongside the scraper runs.

## Weekly snapshots and deltas

The score itself is a snapshot. The product is the *delta* — who dropped thirty points since last week, who flipped from Healthy to Watchlist, which categories are losing ground in aggregate. A single run is a moment; a series of runs is a story.

### Snapshot format

`snapshot.py` reads `output/signals.json` and writes two things per run:

- `snapshots/YYYY-MM-DD/signals.json` — a verbatim copy of the run's output. Full fidelity: every notes field, every news headline, every score component preserved so historical audits never lose context.
- A row per company appended to `snapshots/history.csv` — a tidy long-format table with the columns that matter for time series (`snapshot_date, name, normalized_website, status, survival_score, signal_coverage, website, category`). One row per (company, week). This is the join-friendly layer for charts and trend analysis.

The dual-storage design is deliberate. JSON is the fidelity layer; CSV is the queryability layer. Diffs read the JSONs pairwise; any downstream chart, trendline, or category-level analysis reads the CSV.

### Identity matching across snapshots

A company's identity is its **normalised website** (lowercased host, no scheme, no `www.`, no trailing slash). When the website is missing, the lowercased name is the fallback. This is the same normalisation used by `seeding/merge.py`, so the snapshot join is consistent with dedup across the rest of the pipeline. If a company changes domains between runs, the CSV tracks it as a drop + an add — which is the correct behaviour, because domain migrations are themselves an event worth noticing.

### Delta reports

`diff.py` compares two snapshots (by default the two most recent dated directories under `snapshots/`) and writes a markdown report to `snapshots/diffs/<to_date>.md`. The report has five sections:

1. **Distribution delta** — counts per status, prior → current, with signed change.
2. **Status changes** — who moved bucket, sorted severity-first (deaths, demotions, promotions). A score can drift by twenty points and stay in Watchlist; that matters less than a five-point drift that tips Healthy into Watchlist. The status bucket is the decision-relevant unit.
3. **Biggest score drops** (status unchanged, Δ ≤ −`min-move`) — the quieter movers. Default threshold is five points, which filters out signal noise.
4. **Biggest score gains** (status unchanged, Δ ≥ +`min-move`).
5. **New and dropped entries** — seed-list changes between runs.

Rerunning with an explicit `--from` / `--to` pair lets you jump back and compare any two historical snapshots.

### Recommended cadence

Weekly is the sweet spot. Shorter intervals don't produce enough delta to justify the pipeline run; longer intervals miss fast-moving events (a careers page going dark, a wave of trusted-press coverage). The tracker itself takes thirty to sixty minutes for the 577-company set; news can be refreshed separately in under ten.

## How to re-run

```bash
# Full refresh
python tracker.py                                                    # main signals
python tracker_news.py --trusted-sources-file my_trusted.txt         # news (trusted-only is default)
python build_dashboard.py                                            # dense drill-down view
python build_publish.py                                              # recruiter-facing page

# News-only refresh (fast — skip the expensive main tracker)
python tracker_news.py --trusted-sources-file my_trusted.txt
python build_dashboard.py

# Snapshot + delta (run weekly)
python snapshot.py                                                   # freeze today's signals.json
python diff.py                                                       # compare the two newest snapshots
python build_publish.py                                              # re-render with the new delta section

# Seed refresh (when the source list has gone stale)
python seeding/ycombinator.py --out seeding/sources/yc.csv
python seeding/producthunt.py --out seeding/sources/producthunt.csv
python seeding/merge.py --inputs seeding/sources/yc.csv seeding/sources/producthunt.csv \
    --curated data/startups.csv --out data/startups.csv
```

To run in offline-demo mode:

```bash
python generate_sample_data.py
```
