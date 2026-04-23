# AI Startup Survival Tracker

A public-signals survival tracker for the 2023–2025 AI startup cohort. Collects seven cheap, reproducible signals per company (website uptime, Wayback freshness, blog cadence, GitHub velocity, hiring pulse, trusted news coverage, and curated overrides), blends them into a 0–100 triage score, and surfaces which companies are thriving, pivoting, or quietly fading.

**Current dataset: 577 companies** — seeded from YC Work at a Startup (AI-tagged 2023+ batches), Product Hunt AI topic launches, and a hand-curated core of 37 widely-covered names.

## What's in this repo

```
ai-startup-survival-tracker/
├── README.md                 ← you are here
├── METHODOLOGY.md            ← how scoring works, weights, limitations
├── VC_BRIEF.md               ← one-page analysis of the curated core cohort
├── tracker.py                ← main scraper: website / wayback / blog / github / hiring
├── tracker_news.py           ← news scraper: trusted-source Google News RSS queries
├── scoring.py                ← survival score + status labelling
├── build_dashboard.py        ← renders output/dashboard.html (dense drill-down view)
├── build_publish.py          ← renders output/publish.html (recruiter-facing page)
├── snapshot.py               ← freezes signals.json into snapshots/YYYY-MM-DD/
├── diff.py                   ← writes the weekly delta report
├── generate_sample_data.py   ← rebuilds an offline demo dataset
├── my_trusted.txt            ← optional extra trusted news domains (one per line)
├── seeding/
│   ├── ycombinator.py        ← pulls AI-tagged YC companies
│   ├── producthunt.py        ← pulls AI-tagged Product Hunt launches
│   ├── merge.py              ← merges per-source CSVs into startups.csv
│   └── sources/              ← per-source raw CSVs
├── data/
│   ├── startups.csv          ← the merged seed list (577 companies)
│   └── live_verified.json    ← AI cross-checked overrides (browser + news)
├── snapshots/
│   ├── YYYY-MM-DD/           ← one folder per weekly snapshot (full signals.json)
│   ├── history.csv           ← tidy per-company row per snapshot (for trendlines)
│   └── diffs/                ← weekly delta reports (markdown)
└── output/
    ├── signals.json          ← full scored dataset (current snapshot)
    ├── signals.csv           ← same data, flat for spreadsheets
    ├── news.json             ← per-company news signals (separate file for re-runs)
    ├── dashboard.html        ← interactive drill-down view
    └── publish.html          ← recruiter-facing brief + charts + delta
```

## Quick start

### Look at the output

Two views ship out of the box. `output/publish.html` is the recruiter-facing page — brief, charts, drill-down by status chip, and the latest weekly delta if one has been written. `output/dashboard.html` is the dense drill-down — sort by score, filter by status or category, click a row for the full signal breakdown including the source domain of any news hit. Both are self-contained — no server, no external JS or CSS.

### Re-run the full pipeline

```bash
# 1. Seed (only needed when refreshing the source list)
python seeding/ycombinator.py --out seeding/sources/yc.csv
python seeding/producthunt.py --out seeding/sources/producthunt.csv
python seeding/merge.py --inputs seeding/sources/yc.csv seeding/sources/producthunt.csv \
    --curated data/startups.csv --out data/startups.csv

# 2. Enrich — website, wayback, blog, github, hiring
python tracker.py

# 3. News signal — trusted sources only, by default
python tracker_news.py --trusted-sources-file my_trusted.txt

# 4. Render both views
python build_dashboard.py
python build_publish.py

# 5. (Weekly) snapshot + delta report
python snapshot.py                                                   # freezes current signals.json
python diff.py                                                       # compares the two newest snapshots
python build_publish.py                                              # re-render with the delta section
```

Everything uses public, unauthenticated endpoints. No API keys required. Product Hunt has an optional authenticated mode (`PH_TOKEN=xxx python seeding/producthunt.py --mode api`) that resolves product websites, but the default public mode is good enough to seed.

### macOS SSL note

If `tracker_news.py` fails with `CERTIFICATE_VERIFY_FAILED`, run the Python installer's `Install Certificates.command` once. If the problem persists, the script accepts `--insecure` as an escape hatch — acceptable for this workload since we only read public feeds.

## The scoring model in one paragraph

Seven components, each normalised to `[0, 1]`, weighted and averaged. Missing signals are dropped rather than zeroed, so a company that never had a blog isn't penalised for absence. The news component uses a trusted-source allowlist by default — only Tier-1 business / tech / startup press counts toward the signal, which prevents SEO-bait outlets from flipping labels. Curated notes capturing known shutdowns or pivots act as deterministic overrides. See `METHODOLOGY.md` for the full weight table and reasoning behind each choice.

## Pipeline design

The project is split into four single-purpose stages so any one can be re-run without redoing the others:

**1. Seeding** (`seeding/`) — pulls from YC Work at a Startup and Product Hunt, merges them with the hand-curated list, and deduplicates by normalised website (with normalised-name fallback). Produces `data/startups.csv`. Needs refreshing only when the source list goes stale.

**2. Main tracker** (`tracker.py`) — the enrichment pass. Hits each company's homepage, Wayback, GitHub org, RSS feed, and careers page. This is the bulk of the runtime (roughly 30–60 min for 577 rows). Produces `output/signals.json`.

**3. News tracker** (`tracker_news.py`) — a separate pass so news can be refreshed independently of the expensive main tracker. Queries Google News RSS per company, filters titles to on-topic matches, keeps only results from trusted domains, and classifies each hit into death / health / neutral. Produces `output/news.json`.

**4. Dashboard** (`build_dashboard.py`) — reads both JSON outputs, runs scoring, and emits a self-contained HTML dashboard.

## Trust model for news

News is the only signal about a company that isn't self-reported by the company itself. That makes it uniquely valuable (independent view) and uniquely risky (any URL can publish anything). Three rules govern how news is used:

1. **Trusted sources only, by default.** The allowlist is ~33 domains covering TechCrunch, Reuters, Bloomberg, WSJ, NYT, The Information, VentureBeat, Fortune, The Verge, CNBC, plus wire services and the SEC. Extra domains can be added via `my_trusted.txt`. Pass `--allow-untrusted` to opt out of the gate.

2. **Title-based on-topic filter.** Google News RSS returns articles where the query string appears *anywhere* in the article body, which surfaces plenty of noise (xAI articles leaking into an Inflection AI query, for example). A distinctive-token check requires at least one non-generic token from the company name (strip "ai", "inc", "labs", "tech", etc.) to appear as a whole word in the title.

3. **Trust-gated label override.** An untrusted death headline can lower a company's numeric score, but it cannot flip the label to "Likely Dead." That's reserved for trusted sources and curated notes. This prevents clickbait outlets from mislabeling long-tail companies that no Tier-1 outlet has covered.

## Status buckets

- **Thriving** — score ≥ 80
- **Healthy** — 65–79
- **Watchlist** — 45–64
- **Dormant** — 25–44
- **Likely Dead** — < 25, or trusted death headline in last 180 days, or curated death marker
- **Pivoted / Absorbed** — curated note matches acquihire / acquisition / pivot / rebrand
- **Not Yet Enriched** — row exists in the seed list but no signals have resolved yet (typical for newly-added rows before the main tracker has run against them)

See `VC_BRIEF.md` for the narrative analysis of the curated core cohort.

## Status

This is an MVP. Remaining roadmap:

1. ~~Snapshot + weekly delta report~~ — built (`snapshot.py`, `diff.py`). Baseline snapshot already taken; diffs start producing content once a second snapshot lands.
2. LinkedIn job-count deltas (proxied; LinkedIn is hostile to scrapers)
3. App Store / Play Store review velocity for consumer-facing products
4. Crunchbase funding freshness (currently gated behind a paid API)
5. Publish the dataset + brief somewhere subscribers can follow

The goal isn't the score — it's the weekly delta. The interesting finding is always "who dropped 30 points since last week?"
