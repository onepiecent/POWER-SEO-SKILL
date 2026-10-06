# Research notes (2026-10-06)

This document summarises what was found in official sources, the design decisions that follow from it, and the points that remain uncertain. The list of sources, URLs and verification levels is in [`skills/printerval-blog-seo/references/sources.md`](../skills/printerval-blog-seo/references/sources.md).

**Method limitation:** the working environment blocks direct access to `printerval.com`, `developers.google.com`, `ftc.gov`, `gov.uk` and similar sites, so the points below were confirmed through **the search-result summaries of the official pages**, not by reading them in full. Before quoting verbatim or using any of this for a legal decision, open the original page.

## 1. Google: what changed the design

| Finding | Design impact |
|---|---|
| Helpful-content guidance: original information, a complete description, analysis beyond the obvious; sources, expertise; the **Who/How/Why** framework; **trust** is the most important factor in E-E-A-T | The 8-dimension rubric in `helpful-content-editor`; byline/date/source checks; `[EXPERIENCE]`/`[DATA]` required for a point of view of its own |
| Guidance on optimizing for AI features (May 2026): **unique, non-commodity** content has the most influence; the only conditions for appearing are being indexed and being eligible to show a snippet; no special file or markup for AI is needed | No ad-hoc "GEO tricks" in the skills; the experience bank (`experience-bank`) and the `craft` pillar are where differentiation comes from |
| Guidance on AI content (updated 1 Oct 2026, pointing to Quality Rater Guidelines 4.6.5 and 4.6.6): AI helps with research and structuring, but producing many pages without adding value is **scaled content abuse**; facts must be verified; it is advisable to say how the content was created; main content with little effort, originality or value is rated lowest | One cluster = one post, no pages per keyword variant; a human reviewer is mandatory; a hallucination warning in the rubric; no "bulk generation" mode |
| **Site reputation abuse** policy (updated 28 Aug 2026): third-party, sponsored or partner pages that are independent of the site's main purpose or lack close oversight | Posts by sellers, guest authors or sponsors must be under editorial control (stated in the trust part of the rubric) |
| Review-writing guidance: evidence of experience, measurements, pros **and cons**, an explanation of why something is "best" | The `gift-guide` and `choose-guide` formats: every idea has a reason and a drawback; "tested" only when true |
| Visible date: do not refresh dates artificially; match the structured data | Seasonal posts keep one URL, are refreshed every year, and change the date only when the content changes (`editorial-calendar`) |
| Discover: no clickbait, the title states what the content is, images at least 1,200 px wide | Rubric criteria 1 and 8 |
| The "helpful content system" has moved to the archive section of the ranking-systems guidance (merged into core ranking) | Do not promise a "HCU recovery"; the helpful-content guidance remains the reference standard |
| Search Console has a Generative AI report (Jun 2026) | A suggestion to measure AI appearance after publishing |

**Google does not define pillar/cluster or topical authority**, and does not publish an ideal length or indexing times. The corresponding thresholds in the skills are **[Convention]**.

## 2. Legal and advertising (not legal advice)

| Topic | Key points | Rule in `claims_check.py` |
|---|---|---|
| FTC 16 CFR Part 465 (in force 21 Oct 2024) | Bans fake reviews (including AI-generated ones), buying reviews for a set sentiment, undisclosed insider reviews, and company-controlled "independent" review sites | `review_testimonial`, `first_hand_claim` |
| CMA DMCC Act 2024 (from April 2025, CMA208) | Fake reviews, incentivised reviews without disclosure and misleading presentation of reviews are banned practices in themselves | `review_testimonial` |
| FTC Mail/Internet Order Merchandise Rule | A reasonable basis for any stated delivery time; 30 days by default; consent must be sought for delays | `delivery_promise` |
| FTC Green Guides; CMA Green Claims Code | No generic "eco-friendly"; specific claims need evidence | `eco_general`, `eco_specific` |
| ASA CAP Code and advertisers' own websites | Content on a seller's website that is directly connected with selling may fall within the CAP Code; some blog posts may be editorial content | `uk_remit_note`, `superlative_guarantee` |
| USPTO/UK IPO: trademarks | Trademark confusion does not require identical marks | `ip_brand` |
| FTC "Made in USA", Endorsement Guides | Background knowledge (not re-verified in this session) | `made_in`, `disclosure` |

## 3. Seasonal demand data

NRF 2026 surveys (via search summaries; **re-check the original page before quoting**): Mother's Day expected at about $38 billion (a record), Valentine's about $29.1 billion, Halloween about $13.5 billion; shopping online is the top or joint-top place to buy for several occasions. Use this only as context for prioritising seasonal posts, not as evidence about rankings.

## 4. Errors in search results that were caught

Search summaries returned "Mothering Sunday 2026 is 19 March" and "Father's Day 2026 is Wednesday 21 June": **both are wrong** (Mothering Sunday 2026 is Sunday 15 March; Father's Day 2026 is Sunday 21 June). That is why holiday dates are **computed by rule** and have tests that check them against the real calendar (`tests/test_pipeline.py`). The lesson: do not use figures or dates from search summaries without cross-checking them.

## 5. About Printerval

`printerval.com` could not be accessed, so it was not analysed directly. From search results: a print-on-demand marketplace with independent sellers; URLs come in several styles (`/slug-p<id>`, `/c/...`, `/market/<keyword>`, `/<locale>/`); many product titles are entered by sellers, long and stuffed with keywords; self-reported figures are inconsistent. At the user's request, URLs, the sitemap and technical audits are **out of scope**. Assumptions and open questions: [`printerval-context.md`](../skills/printerval-blog-seo/references/printerval-context.md).

## 6. What could not be done / what is uncertain

- The official pages were not read in full (they are blocked); every level **S** entry should be re-confirmed before being used for a major decision.
- The taxonomy (occasion, recipient, interest, product) is a starting point based on general knowledge of gifting/POD and has not been checked against Printerval's real catalog.
- The heuristic thresholds (readability, link density, the 12/6-week lead time, slot density) are **[Convention]**: calibrate them with the site's own data.
- Clustering by vocabulary does not understand deep synonymy; results are best when real SERP overlap is available.
- The IP list is only a starting sample; legal needs to maintain it.
