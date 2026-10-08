# Checking the SERP without an API

Two keywords are one post when Google ranks the same pages for both; two posts on one SERP split their signals [Google: the live SERP; a page per query]. The threshold used here, **at least 4 shared URLs in the top 10**, is a [Convention] (vendors use 3 to 5). This page is the procedure when the team has no SERP API and no budget: the SEO (or Claude in Chrome on their computer) looks keywords up in a browser.

## Why not check everything

In the SEO's browser check of the Halloween plan (2026-10-08, google.com `gl=us` from a Vietnam IP, top 7-8 organic results), 53 keyword pairs were compared. **46 only confirmed what the plan already did**; 7 changed it (6 merges, 1 merge undone). Reading whole result pages for 53 pairs also costs many tokens. So the skill checks in three layers.

## Layer 1: rules, no lookup

The words that differ between the main keywords of two groups decide when the SERPs checked so far agree (`keyword-clustering/assets/taxonomy.json`, `modifier_rules`; tokens are stemmed):

| The words that differ | Checked pairs (Halloween US) | Rule |
|---|---|---|
| A **segment** word (any word that is not a tone word): a number (`for 4`, `3 group`), who (`male`, `girl`, `adult`, `kids ... for school`), a character, decade or setting (`80s`, `alien`, `clown`, `for work`, `pregnancy`) | 30 of 32 had different SERPs (the 2 that matched were captions at 20 searches/month) | kept apart, no lookup (`segment_modifier`) |
| Only **tone** words (`cute`, `short`, `funny`, `scary`...) and both keywords are a **list topic** (`jokes`, `captions`) | 6 of 6 shared >= 4 | merged, no lookup (`tone_variant`) |
| Only tone words on another topic (costumes, wishes) | costumes 4 of 11 shared >= 4; `cute halloween wishes` 3 of 7 | **looked up** (SERP To-do) |

Level: [Research: the SEO's SERP sample above, one season and one market; Convention for the tone words not observed]. Add a list topic (for example `quotes`, `puns`) only after its own pairs were checked and matched; write the counts in `_comment`.

## Layer 2: the SERP To-do sheet

`export_plan.py` (run by `run_plan.py`) lists the keywords whose SERP can still change the plan:

- the pairs the rules left open: possible duplicates of the SEO's groups (`seo-audit.csv`), groups the topic map merged as the same subject after setting angle words aside (`easy`, `best`: `seo-audit-topic.csv`), and for a raw export the pairs near the merge threshold (`serp-check.csv`);
- only pairs whose **smaller side has >= 100 searches** (`--serp-min-volume`): below that the group is a section of a post whatever the SERP says;
- the biggest decision first, **one lookup per keyword** for all its pairs (the head `trio halloween costumes` once for 4 pairs), at most `--serp-budget` keywords (default 25), and never a keyword already in `--serp`.

On the Halloween file this asks for 22 keywords (16 pairs), against 53 pairs and 5 keywords checked by hand before.

## Layer 3: one lookup, about ten short lines

For each row of SERP To-do:

1. Open its **Google URL** (`https://www.google.com/search?q=...&gl=us&hl=en`; UK: `google.co.uk ...&gl=uk&hl=en-GB`). A logged-out or private window reduces personalisation.
2. Run `assets/serp-extract.js` on the page:
   - **Claude in Chrome:** navigate to the URL, run the file's content with the JavaScript tool, and keep only the returned lines. Do not read the page or take screenshots: the script's answer is all the check needs.
   - **By hand:** paste the file in the DevTools console, or save it once as a bookmarklet (a bookmark whose URL is `javascript:void(` + the file's content + `)`) and click it on each results page. The rows are copied to the clipboard and shown in a box at the top of the page.
3. Paste the lines under the header of `assets/serp-template.tsv` (or into a Google Sheet with the same columns: keyword, market, position, url, title, checked_at, source).

Look keywords up one at a time, at a human pace. Do not script bulk queries to Google: its terms forbid automated access that ignores the machine-readable instructions of its pages (robots.txt), and it answers with captchas [Legal: not legal advice; the terms were read through a third-party summary, see `sources.md`]. Stop when a captcha appears.

Then re-run the same command with `--serp serp.tsv` (repeatable; CSV or .xlsx, sheet `SERP`; one row per keyword with a `serp_urls` column is read too):

- **>= 4 shared top-10 URLs:** one post (`same_query`, evidence `serp`, in seo-audit.csv);
- **fewer:** two posts (`serp_apart`), and `clusters.csv` `keep_apart_from` stops the topic map from merging them as the same subject (`kept_apart`). A group under 100 searches can still become a section of another post;
- sheet **SERP Check** shows every pair of checked keywords that the rules compared or that ask nearly the same words: shared URLs, verdict, both STTs, and `Plan Follows` (`yes`, `no: merged`, `no: apart`). Any `no` needs a look (a decision may override the SERP);
- the checked keywords leave SERP To-do; the rest of the budget goes to the next pairs.

## Keep the file

`serp.tsv` is the team's SERP memory: pass it again on the next run of the same topic, and next year's season re-uses most of it. SERPs move with the season (a Christmas SERP in July is not the one in December): `checked_at` dates every row, and the latest check of a keyword wins. Re-check a season's heads close to the season.

## Limits

- A browser in Vietnam with `gl=us` is close to, not the same as, a US searcher's SERP (location, personalisation). Note it in `source`.
- Claude's web search is not a Google SERP: never record overlap counts from it.
- The modifier rules come from one season and one market; the SERP Check sheet of each new plan is the data to confirm or change them.
- With a budget later, a SERP API export (keyword + top-10 URLs) goes in through the same `--serp` option.
