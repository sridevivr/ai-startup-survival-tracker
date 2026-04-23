# Where do all the AI startups go?

*Notes from building the AI Startup Survival Tracker. What worked, what broke.*

**TL;DR:** I built a tool that tracks 577 AI startups and scores how alive each one is, using AI as my co-builder. This post walks through the moments that mattered, where the AI moved the project forward, and where I had to stop and rethink what it handed me.

---

Every day there's a new AI startup. LinkedIn, podcasts, the group chat, my inbox, all saturated with "we're using AI to solve X." Which is fine. But I kept wondering about the silent middle of that sentence. What actually happens to all these companies after they launch?

Which ones are still shipping? Which ones have quietly gone dark? Which ones were absorbed in an acquihire that didn't make the news? The AI industry has been booming for a couple of years now. The interesting question at this point is who's still here twelve months later.

I'm a program manager by background, not an engineer. My first instinct was to find someone else's list. But the real lists don't exist. TechCrunch covers the top of the funnel, Crunchbase is paywalled, YC tells you who joined but not who stayed. So I decided to build one, using AI as my co-builder.

This post isn't really about what the tool found. The findings are [on the live dashboard → *your URL*]. This is about what it looked like to build it. The moments where the AI did what I needed, and the moments where I had to push back.

---

## 1. The first list was the wrong list

The AI's first list was 37 famous AI companies, names I already recognized. The point was to learn about everyone else, so I started asking about other possible sources. I suggested YC, since it's an incubator where a lot of AI startups get their start. Filtering its Work-at-a-Startup directory for the AI tag across 2023+ cohorts, adding Product Hunt's AI launches, and deduping got us to 577 real names.

**Worked:** Once I gave it the right source, the AI wrote the scraper in an afternoon.
**Broke:** The first framing was a short list of famous names. I had to do the scoping myself.

## 2. Seven signals, one that kept breaking

The AI proposed six public signals anyone could check by hand. Website uptime, Wayback Machine freshness, blog cadence, GitHub commits, careers-page activity, curated notes. I added a seventh: news. The other six measure what the company says about itself. News reflects the outside world's view, which makes it the most useful signal and the most dangerous.

**Broke:** The first version of the news scraper flipped three live companies into "Likely Dead" using headlines from outlets no analyst would trust.

## 3. Trust is something you design

The fix was an allowlist. I sat with the AI and we built it in four buckets: startup and VC press, business and financial, tech press, and primary sources like SEC filings and wire services. Thirty-three domains total. I added a second rule too. An untrusted death headline can lower a company's score, but it cannot flip the label to "Likely Dead." That privilege is reserved for trusted sources and curated notes.

**Worked:** The AI helped me think through edge cases and surfaced outlets I'd missed.
**Broke:** The first list was too permissive. Trust has to be designed deliberately.

## 4. Ten companies before 577

I didn't want to run the pipeline against all 577 companies on the first pass. Too many things could break at once. So I ran it against ten, and the test caught several issues: a regex that failed on apostrophes in company names, a GitHub API call that silently returned zero commits for orgs with unusual capitalization, and one company whose "website" in the YC directory was literally "N/A."

**Worked:** Using the AI to patch each bug as it surfaced.
**Broke:** Every "let's just run the whole thing" impulse.

## 5. What do the signals actually mean?

Flowing data is one thing. Deciding what it means is another. The AI's first scoring draft counted missing signals as zeros, so a company that never had a blog got penalized for not having one. Quiet-but-alive companies scored too low. I asked the AI to drop missing signals from the weighted average instead, and the distribution looked sensible within an hour.

**Worked:** The AI is good at taking a spec and building it.
**Broke:** The default behavior the AI reached for was wrong for my case. If I'd trusted the first run, the scoring would have been subtly wrong for the long tail.

## 6. "Verified" was the wrong word

Late in the project, the dashboard showed a badge: "7 companies verified." It meant that for seven entries, a Claude-in-Chrome session had navigated to each company's site and cross-referenced its status against press coverage. One of the seven was Codeium. I didn't remember verifying Codeium. That triggered the question: what does "verified" mean here?

The honest answer was that a Claude-in-Chrome session verified it. Not me. Someone looking at my dashboard would reasonably assume I had personally reviewed each case. I hadn't. So we renamed it to **AI cross-checked**. It was one of the most important edits in the whole project, and it came from noticing a single word that felt off.

**Worked:** Claude-in-Chrome is a strong tool for this kind of check.
**Broke:** "Verified" overstated what happened. "AI cross-checked" described it accurately.

---

## What this whole thing taught me

The tracker is live. 577 companies, seven signals each, a weekly snapshot so I can watch the deltas over time.

What working on this taught me, three things. **AI produces excellent first drafts; getting to the right answer takes more work.** Every time I accepted the first framing I got a demo. **Trust has to be designed.** The AI built each layer of the trust model fine. I had to specify what trust meant. **Honest language is cheap and important.** Catching "verified" came from knowing which specific cases the word would apply to.

The first real delta report lands seven days from now.

---

*[Live dashboard →](your-url)  ·  [Source code on GitHub →](your-url)  ·  [Portfolio →](https://sridevivr.com)*
