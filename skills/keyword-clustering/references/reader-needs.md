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

- A keyword that is only a product name with an adjective ("funny dad shirts") is labelled `shop`; if the SERP is full of guides or ideas, change it by hand to a blog post.
- A policy question ("how long does shipping take") belongs to `info` but it is service content: it needs operational data and must not be written from guesswork (see `claims-compliance-check`).
- The `info` need can have very large seasonal volume ("when is mother's day") but competes with Google's direct results; it is usually best as a short section in a pillar post.
