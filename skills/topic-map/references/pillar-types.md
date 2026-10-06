# Pillar types for a POD blog (and expected coverage)

This is an **organisational framework [Convention]**. The common rule: a pillar must carry value of its own (help the reader decide), not just be a list of links.

| Pillar type (`pillar_type`) | Examples | Suggested name | Expected coverage (a gap is reported if missing) |
|---|---|---|---|
| **occasion** | mothers-day, christmas, halloween | "{Occasion} Gift Ideas" | gift guides by recipient/budget; slogans and card messages; informational questions (date, meaning) |
| **interest** (hobby/passion) | dogs, fishing, gaming | "Gift Ideas for {Audience}" | gift guide; slogans/quotes; how-tos on personalisation, design or care |
| **recipient** | mom, teacher, nurse | "Gift Ideas for {Recipient}" | gift guide; slogans/messages |
| **craft** (specialist knowledge) | sizing, care, print-methods, design | "Sizing & Fit Guide", "Care & Washing Guide"... | how-to/solve; explanations and comparisons (info/choose) |
| **inspiration** (wording ideas) | slogans, quotes, captions | "Slogans, Quotes & Caption Ideas" | by tone, relationship or occasion |
| **product** (by product, the last tier) | shirts, mugs | "{Product}: Ideas & Guides" | gift guide + how-to |
| **category** (user-defined) | Pets, Work & school | the name of your group | depends on the brief |

## Why there are "craft" and "inspiration" pillars

- **craft** is where Printerval has real experience (printing, materials, sizing, care, personalisation). Google favours content with a point of view and first-hand experience ("non-commodity"); these are the posts that a generic summary cannot easily replace. Every claim specific to Printerval's products must come from the product team's documents.
- **inspiration** (slogans, quotes, captions, card messages) is useful independently of buying and leads to custom products very naturally (readers need words to put on a shirt or mug). Use original wording; do not copy song lyrics, film lines or brand slogans.

## A good hub (pillar post)

- The first screen helps a reader who only has 30 seconds: "If you need X, read Y".
- Every cluster gets 2-3 summary sentences and one contextual link; do not repeat the cluster's content.
- A seasonal pillar **keeps one URL and is refreshed every year**; change the visible date only when the content really changes (Google: do not refresh dates artificially).
- A pillar with more than 30 clusters: split it into sub-hubs (for example by recipient) instead of one endless page.

## Cross-links between pillars

A cluster whose second facet matches another pillar (for example "Mother's Day gift ideas for dog moms" belongs to the Mother's Day pillar but has `interest=dogs`) gets a cross-link to the interest pillar proposed by `internal-link-planner` (type `cross_pillar`). Keep at most 1 cross-link per post so it does not get diluted.
