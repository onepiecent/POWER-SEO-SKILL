# Reader need (`reader_need`) and blog fit (`blog_fit`)

Every keyword is assigned exactly one need by regex rules (priority order from top to bottom; the rules live in `assets/taxonomy.json` -> `reader_need_rules`). This is a **heuristic [Convention]**: confirm it against the real SERP for the clusters that matter.

| `reader_need` | Signals | Examples | `blog_fit` | Typical post type |
|---|---|---|---|---|
| `shop` | buy, order, cheap, discount, coupon, price, wholesale, near me; or only a product name (with a style) | "custom mugs", "buy personalized mug" | **low** | Dropped from the blog map: handled by the shop pages / content team |
| `how_to` | how to, DIY, steps to, ways to, tutorial | "how to wash a graphic tee" | high | how-to |
| `copy_ideas` | slogans, quotes, captions, sayings, taglines, what to write, name ideas | "funny t shirt slogans", "mother's day quotes" | high | copy-ideas |
| `choose` | best, vs, which, review, compare, worth it, buying guide | "dtg vs screen printing", "best gifts for nurses" | high | choose-guide or gift-guide |
| `solve` | fix, remove, shrink, fade, wash, care, size, fit, stain | "t-shirt size chart men" | high | how-to |
| `inspire` | ideas, gifts, presents, what to get | "gifts for dog lovers", "mother's day gift ideas" | high | gift-guide, ideas-list, pillar-hub |
| `info` | what/why/when/where/who..., meaning, history, date | "when is mother's day", "what is dtg printing" | medium | explainer (often just a section inside a pillar post) |

## Clustering by need

`inspire` and `choose` are treated as the same "list" group (the reader wants a list with reasons to choose): "best gifts for nurses" and "gifts for nurses" can go into the same cluster. The other needs must match exactly to merge ("how to wash" does not merge with "what is DTG").

## When to doubt a label

- A keyword that is only a product name with an adjective ("funny dad shirts") is labelled `shop`; if the SERP is full of guides or ideas, change it by hand to a blog post. When the export carries the tool's intent or SERP features, the script already does part of this (next section).
- A policy question ("how long does shipping take") belongs to `info` but it is service content: it needs operational data and must not be written from guesswork (see `claims-compliance-check`).
- The `info` need can have very large seasonal volume ("when is mother's day") but competes with Google's direct results; it is usually best as a short section in a pillar post.

## Regex vs the tool's intent (`need_source`)

The regex is not the only evidence when the export has an intent or SERP-features column (Semrush Intent / Keyword Intents, Ahrefs Intents or true/false intent columns, SERP Features). Semrush and Ahrefs assign intent with their own models from the SERP and the words [Convention: vendor docs]; a label is a hint, not proof, and is least reliable on ambiguous and low-volume keywords.

- **Never drop on regex alone.** When the regex says `shop` only because the keyword names a product (the product fallback, not a buy/price/coupon rule), and the tool's intent includes `informational` or `commercial`, or the SERP features include People also ask, a featured snippet or an AI Overview, the need is computed again without the product fallback. The keyword stays in the blog plan with that need, and `need_source` in `keyword-map.csv` says why: `conflict: regex shop vs semrush commercial+informational` or `conflict: regex shop vs SERP features paa`. The report counts these conflicts.
- Otherwise `need_source` = `rule`. A keyword that hits an explicit shop rule (buy, cheap, coupon, near me...) stays `shop` whatever the tool says, and a file with no intent or SERP-features column behaves exactly as before ("custom mugs" stays `shop`, `blog_fit=low`).
- **Review each conflict**: open the live SERP for the bigger ones. If it is all product listings, the keyword belongs to the shop pages; if it shows guides, ideas or questions, write the post for the need the script chose (or a better one) and state the angle.
