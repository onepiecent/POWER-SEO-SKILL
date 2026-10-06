---
name: content-brief
description: Generates and completes English content briefs for the Printerval blog from the topic map (metadata, keywords, outline by post type such as gift guide, ideas list, choose guide, how-to, explainer, copy ideas or pillar hub, internal links, product slot plan, compliance flags, publish deadline). Use when the user needs a brief, an outline, help preparing an article or a hand-off to writers, or after a topic map or link plan exists.
---

# Content brief

A brief is the **quality contract** between SEO and the writer: what the reader needs, what the post must contain, what makes it different, and what it must not do. The script fills in what can be computed; Claude or the SEO fills in what needs the real SERP and Printerval's real first-hand experience.

## Workflow

1. **Generate the skeleton:**
   ```bash
   python3 skills/content-brief/scripts/make_brief.py --topic-map outputs/topic-map.csv \
       --link-plan outputs/link-plan.csv --seasonal-plan outputs/seasonal-plan.csv --bucket A --limit 10 --out outputs/briefs
   python3 skills/content-brief/scripts/make_brief.py --topic-map outputs/topic-map.csv --slug mothers-day-gifts-for-grandma
   ```
   A post that absorbed other clusters in the topic map (`role=merged`) lists them under **"Also covers"** in the Keywords section: answer them as sections or FAQs of the same post, never as separate thin pages.
2. **Fill in the `[TO FILL]` sections** (see `references/serp-review.md`):
   - Who the reader is and what situation they are in; what would make them close the tab disappointed.
   - The real SERP on google.com (US) or google.co.uk (UK), **never searched from a Vietnamese IP**: the winning format, what the competitors do well and **what they miss** (the content gap), and the People Also Ask / AI Overview questions to answer **inside the same post** (not split into thin pages).
   - **The first-hand angle**: ask the questions in the "First-hand angle" section to the right team (support, design, QC, operations); record `[EXPERIENCE: source]` or `[DATA: source]`. If nothing is available, say so plainly and tell the user; **never invent it**.
   - Sources to cite (prefer primary sources: .gov/.gov.uk, standards bodies, verifiable surveys, product-team documents).
   - Two or three title/meta options; measure them with `seo-content-vn/scripts/seo_check.py`.
3. **Check the brief** before handing it over: is there at least one feasible source of first-hand experience or original data? Have the compliance flags been read? Do the internal links match the plan? Are the market and the English variant right?
4. **Hand it to the writer or AI** together with the skills `helpful-content-editor` (helpfulness criteria), `product-slot` (how to mention products) and `english-grammar-style` (English editing).

## Post formats (`assets/formats/`)

| `post_type` | When to use | Characteristics |
|---|---|---|
| gift-guide | gifts by occasion, recipient or interest | grouped by reason or personality; every idea has a reason it fits, pros and cons; no fixed prices |
| ideas-list | ideas that are not gifts | quality over quantity; every item has a distinguishing detail |
| choose-guide | X vs Y, best X, how to choose | verdict first; criteria; comparison table; drawbacks; "tested" only when true |
| how-to | how to do something or fix a problem | quick answer first; numbered steps; common mistakes; no promised results |
| explainer | what is / when is | a direct answer in the first two sentences; holiday dates must be computed, not guessed |
| copy-ideas | slogans, quotes, captions, messages | original wording; grouped by tone; print limits come from the design team |
| pillar-hub | a hub post for a topic | "Start here"; a summary of every cluster plus one link; refreshed every year |

Every format file has: Skeleton, Rules, **Experience prompts** (internal interview questions) and Product-slot guidance. They are inserted into the brief automatically. The shared experience library is `assets/experience-bank-template.md`.

## Principles for helpful content (summary; details in `helpful-content-editor`)

- Answer early; the post **stays useful with every product slot removed**.
- Include a first-hand or original-data point: Google stresses "non-commodity" content (its own point of view, first-hand experience), which a generic summary cannot replace.
- Do not mass-produce posts for every keyword variant; one cluster = one post (scaled content abuse).
- Statistics need a primary source; never invent them; write `[DATA NEEDED: ...]`.
- If AI helps with the draft: an editor verifies the facts and adds original value; consider saying how the content was created, in a way that suits readers (Google's guidance).
