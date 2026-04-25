# Where do all the AI startups go?

*Notes from building the AI Startup Survival Tracker. What worked, what broke.*

**TL;DR:** I built a tool that tracks 577 AI startups and scores how alive each one is, using AI as my co-builder. This post walks through the moments that mattered, where the AI moved the project forward, and where I had to stop and rethink what it handed me.

---

Every day there's a new AI startup. LinkedIn, podcasts, the group chat, my inbox, all saturated with "we're using AI to solve X." Which is fine. But I kept wondering about the silent middle of that sentence. What actually happens to all these companies after they launch?

Which ones are still shipping? Which ones have quietly gone dark? Which ones were absorbed in an acquihire that didn't make the news? The AI industry has been booming for a couple of years now. The interesting question at this point is who's still here twelve months later.

I'm a program manager by background. My first instinct was to find someone else's list. The real lists don't exist. TechCrunch covers the top of the funnel, Crunchbase is paywalled, YC tells you who joined but not who stayed. So I built one, using AI as my co-builder.

What the tool found is [on the live dashboard](https://sridevivr.github.io/ai-startup-survival-tracker/). This post is about what it looked like to build it. The moments where the AI did what I needed, and the moments where I had to push back.

---

## 1. The first list was the wrong list

The AI's first list was 37 famous AI companies, names I already recognized. The point was to learn about everyone else, so I started asking about other possible sources. I suggested YC, since it's an incubator where a lot of AI startups get their start. Filtering its Work-at-a-Startup directory for the AI tag across 2023+ cohorts, adding Product Hunt's AI launches, and deduping got us to 577 real names.

**Worked:** Once I gave it the right source, the AI wrote the scraper in an afternoon.
**Broke:** The first framing was a short list of famous names. I had to do the scoping myself.

## 2. Seven signals, one that kept breaking

The AI proposed six public signals anyone could check by hand. Website uptime, Wayback Machine freshness, blog cadence, GitHub commits, careers-page activity, curated notes. I added a seventh: news. The other six measure what the company says about itself. News reflects the outside world's view, which makes it the most useful signal and the most dangerous.

**Broke:** The first version of the news scraper flipped three live companies into "Likely Dead" using headlines from outlets no analyst would trust.

## 3. Trust is something you design

The fix was to build a list of trusted news sources whose coverage could meaningfully change a startup's score. Four buckets: VC press, business and financial, tech press, and primary sources like SEC filings and wire services. 33 domains in total.

A second rule had to go in too. Not every trusted publication covers every small startup, so untrusted outlets couldn't be ignored entirely. I allowed an untrusted source to nudge the signal slightly lower if it reported bad news, but it could never flip a label to "Likely Dead." That privilege was reserved for trusted sources and curated notes.

**Worked:** The AI helped me think through edge cases and surfaced outlets I'd missed.
**Broke:** The first list was too permissive. Trust has to be designed deliberately.

## 4. Ten companies before 577

I didn't want to run the pipeline against all 577 companies on the first pass. Too many things could break at once. So I ran it against ten, and the test caught several issues: a regex that failed on apostrophes in company names, a GitHub API call that silently returned zero commits for orgs with unusual capitalization, and one company whose "website" in the YC directory was literally "N/A."

**Worked:** Using the AI to patch each bug as it surfaced.
**Broke:** Every "let's just run the whole thing" impulse.

## 5. One axis wasn't enough

The dataset started with one tag per company, and for most of them that tag was just "AI." Not useful. A keyword pass against each tagline turned most of those into something specific like Finance or Healthcare or Legal. For the ambiguous rows, I ran a scraper against each company's homepage and used an LLM to assign a tag from the content.

Then I looked at the distribution and noticed a problem. About half the cohort landed in what I was going to call Cross-industry: developer tools, agent platforms, foundation models, general LLM infrastructure. Products sold across industries rather than to one vertical. A single-tag view was going to hide half the story.

The fix was a second axis. **Sector** names the industry a company serves (Healthcare, Finance, Legal, Consumer, and so on, with Cross-industry for the cross-vertical tools). **Function** names where the company sits in the AI stack: Foundation Models, ML Infrastructure, Data Infrastructure, AI Agent, Copilot, Generative Product, Analytics, Research Lab. With both axes populated, the heatmap told a real story. About half the cohort is Cross-industry. Inside that half, AI Agents dominate. The vertical plays concentrate in Healthcare and Finance. A one-axis view would have flattened all of that.

**Worked:** A Python scraper (requests plus BeautifulSoup) pulled each homepage's title, h1, and first paragraph in parallel. One batched LLM call classified all 577 companies on both axes in under a minute. Cheap and repeatable.

**Broke:** The first version of the classifier worked only from the tagline, which was often a single line like "The AI workforce for finance teams." Not enough signal to tell if the product was an agent, a copilot, or a decision tool. Adding homepage content fixed it.

---

## What this whole thing taught me

The tracker is live. 577 companies, seven signals each, a weekly snapshot so I can watch the deltas over time.

Three things I'll carry forward:

- **AI produces excellent first drafts; getting to the right answer takes more work.** Every time I accepted the first framing I got a demo, not an answer.
- **Trust has to be designed.** The AI built each layer of the trust model cleanly. Specifying what trust meant was mine to do.
- **One label isn't enough.** Most single-axis classifications hide as much as they reveal. Pairing sector with function changed what I could actually see in the data.

The first real delta report lands seven days from now.

---

*[Live dashboard →](https://sridevivr.github.io/ai-startup-survival-tracker/)  ·  [Source code on GitHub →](https://github.com/sridevivr/ai-startup-survival-tracker)  ·  [Portfolio →](https://sridevivr.com)*
