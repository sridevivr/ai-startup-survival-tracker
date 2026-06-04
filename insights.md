# YC AI Momentum Heatmap — Insights

Numbered findings as we go. These are the editorial spine — they're what
ends up at the top of `output/momentum.html` in Step 5.

## TL;DR

*(Filled in at Step 5. The 5 most-quotable findings from below.)*

---

## I-1 · Cohort shape — what survives the cut

We started with 578 YC AI startups. We focused on the **post-ChatGPT
founder generation** by filtering to companies founded in 2023 or later
(534 remain). We dropped 63 marked dead, pivoted, or dormant. We dropped
327 more that show zero positive momentum signals over the last 180
days. **144 companies** clear the bar.

### Density at a glance

| sector × functionality | n |
|---|---|
| Cross-industry × AI Agent | 20 |
| Cross-industry × ML Infrastructure | 11 |
| Finance × AI Agent | 11 |
| Cross-industry × Data Infrastructure | 9 |
| Cross-industry × Generative Product | 9 |
| Customer Support × AI Agent | 9 |

### Three observations to carry forward

1. **Cross-industry is still 65 of 144 (45%).** Cutting the cohort
   didn't reveal a vertical/horizontal split — it preserved it. Step 4
   has to open this box.
2. **AI Agent is the dominant functionality** — 60 of 144 (42%). The
   post-ChatGPT wave has converged on agentic patterns. Whether that's
   substantive or fashion is something Steps 2–3 (activity, funding)
   will help answer.
3. **Finance × AI Agent is the strongest *vertical* cell** (11
   companies). Worth watching closely once activity and funding layers
   come in.

---

## I-2 · *(Step 2 — signal density across the grid)*

*Pending. Will populate after Step 2 runs.*

## I-3 · *(Step 3 — where the money has actually gone)*

*Pending.*

## I-4 · *(Step 4 — what "Cross-industry" actually means)*

*Pending.*

## I-5 · *(Step 5 — four lenses, four different stories)*

*Pending.*

---

## Methodology (short version)

- **Cohort cut:** founded ≥ 2023, status ∉ {Likely Dead, Pivoted/Absorbed,
  Dormant}, **≥ 1 positive momentum signal** (recent news, fresh site,
  hiring, fresh blog, or active GitHub).
- **Single source of truth:** `data/master.csv`. Grows column by column.
- **Visual:** `output/momentum.html`. Built progressively; always openable
  in a browser. Magazine-spread aesthetic — Fraunces display serif, Geist
  body, terracotta accent.
- **What was NOT done:** no paid APIs, no LinkedIn / Twitter scraping, no
  re-touching of the survival pipeline.
