# Seeding Methodology

## Why this module exists

The first version of `data/startups.csv` was hand-picked from memory — 37
companies I (or the operator) happened to know about. That approach has three
problems a VC-facing tool cannot afford:

1. **Not reproducible.** If someone else re-runs the tracker next month, they
   have no way to regenerate the same seed list. "Famous AI companies I
   recall" is not a query.
2. **Survivorship-biased.** Memory over-weights the winners (OpenAI,
   Anthropic) and the famous failures (Humane, Inflection). The silent
   middle — the 2023 seed-stage AI company that quietly shut down in
   month 14 with zero press — is precisely the cohort a survival tracker
   exists to catch, and they are systematically missing from any "companies
   I remember" list.
3. **Uncounted unknowns.** If the list is hand-curated, we cannot measure
   coverage. We don't know whether we're tracking 5% or 50% of the 2023–2025
   AI cohort.

The seeding module replaces "what I remember" with "what public directories
already track." It pulls from multiple sources with disclosed biases, merges
them with URL-based deduplication, and leaves a per-source provenance column
so the downstream reader can see which source flagged each company.

## Source selection

Every source we add carries its own bias. The point is to layer sources with
*different* biases so that the shape of the blind spot changes. If YC biases
toward US early-stage, Product Hunt biases toward consumer products with
good marketing, then the intersection tells us nothing but the *union* covers
both blind spots.

| Source | What it over-represents | What it misses | Provenance strength |
|---|---|---|---|
| **Y Combinator** | US-based, accelerator-backed, early-stage, 2020–2025 cohort, heavy B2B SaaS | Non-YC founders; European/Asian startups; post-seed companies that raised elsewhere; anyone who was rejected or didn't apply | Very high — YC publishes batch + status directly |
| **Product Hunt** | Consumer AI products, strong marketing, v1-launch companies | B2B / infra companies, quiet-launch products, post-launch pivots | Medium — launch date is clean, status is not tracked |
| **Crunchbase / Pitchbook** | Funded companies with public announcements | Bootstrapped companies, stealth companies; gated behind paid API | Gold standard (paid) |
| **Academic / GitHub stars (future)** | Research-heavy AI companies with open-source presence | Closed-source product companies | High for a specific niche |

Today the module ships with YC and Product Hunt adapters. Crunchbase is a
stub (`crunchbase.py` commented-out) and academic/GitHub sources are listed
as future work.

## YC adapter — what it does

YC's company directory at `ycombinator.com/companies` is rendered client-side
via Algolia search. The Algolia App ID and a restricted search key are
visible in the page HTML (this is how Algolia client-side search always
works — the key is scoped to read-only access on the public index). We hit
the same Algolia endpoint the YC UI hits, with the same facet filters the
URL query string exposes.

Query: `tags:Artificial Intelligence` ∩ any-of `batch:Winter 2023`
through `batch:Fall 2025`.

At last run (April 2026) this returns **539 companies**, with YC's own
status field already distinguishing:

- **Active:** 497
- **Inactive:** 24  (YC's label for shut-down / dissolved)
- **Acquired:** 18

That means **42 of 539 YC-alumni AI companies in the 2023–2025 cohort are
already flagged non-active by YC itself** — direct ground truth for the
failure cohort before the survival-signal scraper runs. These are the companies
most worth studying as examples of how silent shutdowns happen: most of them
have had zero press coverage, and would never have appeared on a hand-picked
list.

See `seeding/sources/yc.csv` for the current cached sample. To refresh:

```bash
python seeding/ycombinator.py --out seeding/sources/yc.csv
```

The script is intentionally dependency-free (stdlib only) so it runs on any
box with Python 3.9+.

## Product Hunt adapter — what it does

Product Hunt indexes product *launches*, not companies. That's a different
shape of data: a company can launch three products on PH and still count
once in our seed (we dedup by domain). The useful columns PH gives us:
launch date, tagline, upvotes at launch (crude popularity signal), and the
linked-out website.

Product Hunt's GraphQL API requires an OAuth app registration, which is
heavier than YC's "load the page, steal the key" approach. The adapter
therefore has two modes:

1. **Topic-scrape mode** (default, no auth): navigate PH's public AI topic
   pages (`/topics/artificial-intelligence`, `/topics/generative-ai`) and
   extract product name + URL from the rendered cards. This is brittle to
   PH's UI changes but works without credentials.
2. **API mode** (optional): if the user registers a PH API app and sets
   `PH_TOKEN` in their environment, the adapter uses the GraphQL endpoint
   which is more stable.

See `seeding/producthunt.py` for details.

## Dedup + merge

After each source has populated its CSV under `seeding/sources/`, the merge
step in `seeding/merge.py` normalizes URLs and joins into the final
`data/startups.csv`.

URL normalization rules (primary key for dedup):

- Strip `http://` or `https://`
- Strip leading `www.`
- Strip trailing slash and path/query if present
- Lowercase the resulting host

So `https://openai.com/`, `http://www.openai.com`, and `openai.com/about`
all collapse to the same key: `openai.com`.

When a company appears in multiple sources, we keep all fields and add a
pipe-joined `sources` column (e.g. `ycombinator|producthunt`). This is
information-preserving — downstream the tracker can weight a company
differently if it appears in three sources vs. one.

When a company has *no* website (rare; a few YC companies), we fall back to
the company name (lowercased, non-alphanumeric stripped) as the dedup key,
with a warning logged.

## What this module explicitly does not claim

- **Not exhaustive.** Neither YC nor Product Hunt cover the full 2023–2025
  AI cohort. Many startups raised outside YC and never launched on PH. The
  output is "a reproducible, transparent, bias-disclosed sample," not
  "the universe of AI startups."
- **Source labels are inputs, not verdicts.** YC calling a company "Inactive"
  is a strong signal, but still needs the news-cross-check layer described
  in `METHODOLOGY.md` before anything lands in a VC-facing output.
- **Refresh cadence is your responsibility.** Re-run the adapters monthly
  and commit the diff. The delta between monthly seeds is itself a useful
  signal (new YC batches, new Inactive flags).

## Directory layout

```
seeding/
├── SEEDING.md           ← this file
├── ycombinator.py       ← YC adapter (stdlib only)
├── producthunt.py       ← Product Hunt adapter
├── merge.py             ← URL-normalized dedup + final startups.csv
└── sources/
    ├── yc.csv           ← YC-sourced rows (cached last run)
    └── producthunt.csv  ← PH-sourced rows (cached last run)
```

## Re-running end-to-end

```bash
python seeding/ycombinator.py --out seeding/sources/yc.csv
python seeding/producthunt.py --out seeding/sources/producthunt.csv
python seeding/merge.py \
    --inputs seeding/sources/yc.csv seeding/sources/producthunt.csv \
    --out data/startups.csv
```
