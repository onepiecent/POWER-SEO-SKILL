# Printerval context and assumptions

This document records what is known, what is **only an assumption**, and the open questions. Update it when real information becomes available.

## Known (from the user's requests)

- Goal: an SEO skill set for the Printerval **blog**, focused on helpful content. No technical audit.
- Markets: **US/UK**, English posts.
- SEO specialists send **CSV exports from very broad keyword groups**; the skills must read them and cluster them on request.
- Printerval's URLs and sitemap are being reworked and there are many redirects: **do not rely on the current URLs or sitemap**.
- Product links are added by the content team; the blog leads readers to the shop naturally.

## Public information (from search results; not verified directly because the environment blocks access to printerval.com)

- A print-on-demand marketplace with independent sellers: apparel, hoodies, posters, canvases, homewares and personalized gifts; multilingual versions (`/es/`, `/uk/`) and a separate help center.
- Self-reported figures are inconsistent between sources (number of creators, number of customers). Do not quote these figures in a post without an official company source.
- A third-party source (Semrush, via search snippets) lists close competitors: ArtistShot, TeePublic, Spreadshirt. The date of the data is unknown.

## Assumptions in use (to be confirmed)

| Assumption | Impact if wrong |
|---|---|
| The blog mainly serves **buyers** (gifts, personalization); there is no post group for sellers or creators yet | A separate topic map is needed for sellers (how to sell POD, design) |
| The default taxonomy (occasion, recipient, interest, product, knowledge) reflects the catalog | Extend it with `--extend-taxonomy` or edit `assets/taxonomy.json` |
| The product catalog is broad enough for gift-guide posts to mention products naturally | Some clusters may have no matching product: the content team reports back |
| Seasonal posts need a 12-week lead time (new posts) / 6 weeks (updates) | Calibrate with seasonality from GSC/Trends |
| The default market is `us` when a file does not state one | Tag UK files as `file.csv::uk` |

## Open questions

1. Where does the blog live (subfolder, subdomain, separate CMS)? How many posts are already published, and is there a slug list so that `link_plan.py --published` knows which posts are live?
2. Is there a separate `/uk/` structure for the UK version? Do UK posts have their own URLs or share them?
3. Who are the authors and editors (byline, bio), and is there a fact-checking process?
4. Who owns the list of IPs and trademarks to avoid, and the operational data (order deadlines, delivery times)?
5. Which keyword data source is in use (Semrush, Ahrefs, Keyword Planner, GSC)? Can it be exported with `serp_urls` so that keywords can be clustered by SERP?
