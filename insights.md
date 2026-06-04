# YC AI Momentum Heatmap — Insights

Numbered findings as we go. These are the editorial spine — they're what
ends up at the top of `output/momentum.html` in Step 5.

## TL;DR

*(Filled in at Step 5. The 5 most-quotable findings from below.)*

---

## I-1 · Cohort shape — what survives the cut

After dropping pre-2023 companies (–44), known dead / pivoted / dormant
(–63), and silent companies with zero positive momentum signals (–327),
we're left with **144 of 578 YC AI startups** with at least one sign of
life in the last 180 days.

Density tells one early story before we even start measuring activity:

| sector × functionality | n |
|---|---|
| Cross-industry × AI Agent | 20 |
| Cross-industry × ML Infrastructure | 11 |
| Finance × AI Agent | 11 |
| Cross-industry × Data Infrastructure | 9 |
| Cross-industry × Generative Product | 9 |
| Customer Support × AI Agent | 9 |

Two observations worth carrying forward:

1. **Cross-industry is still 65 of 144 (45%).** Cutting the cohort
   didn't reveal the horizontal/vertical split — it preserved it.
   Step 4 needs to open this box.
2. **AI Agent is the dominant functionality** — 60 of 144 (42%). The
   wave has clearly converged on agentic patterns post-ChatGPT. Whether
   that's substantive or fashion is something the activity/funding
   lenses (Steps 2–3) will help answer.
3. **Finance × AI Agent is the strongest vertical cell** (11 companies).
   Worth watching once we layer in activity and funding.

---

## I-2 · *(Step 2 — signal density across the grid)*

*Pending.*

## I-3 · *(Step 3 — where the money has actually gone)*

*Pending.*

## I-4 · *(Step 4 — what 'Cross-industry' actually means)*

*Pending.*

## I-5 · *(Step 5 — four lenses, four different stories)*

*Pending.*

---

## Methodology (short version)

- **Cohort cut:** founded ≥ 2023, status ∉ {Likely Dead, Pivoted/Absorbed,
  Dormant}, **≥1 positive momentum signal** (recent news, fresh site,
  hiring, fresh blog, or active GitHub).
- **Single source of truth:** `data/master.csv`. Grows column by column.
- **Visual:** `output/momentum.html`. Built progressively; always openable
  in a browser.
- **What was NOT done:** no paid APIs, no LinkedIn / Twitter scraping, no
  re-touching of the survival pipeline.
