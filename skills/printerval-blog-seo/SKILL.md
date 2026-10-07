---
name: printerval-blog-seo
description: Orchestrates the Printerval blog SEO skill suite (print-on-demand marketplace, US and UK markets, English content). Use when the user talks about the Printerval blog, keyword export files from SEO specialists (CSV or xlsx from Semrush, Ahrefs, Keyword Planner, Search Console), keyword clustering, pillar and cluster planning, topic maps, the final keyword plan sheet for the content team (also matched with the posts already published, and re-run safely on the plan the team works in), internal links between blog posts, content briefs, gift guides, seasonal content calendars (Mother's Day, Christmas), product slots, claim and IP checks, or whether a draft is helpful to readers. Not for technical audits, URLs or sitemaps, or links to product pages.
---

# Printerval Blog SEO: orchestration

This suite helps the Printerval SEO and content team turn a very broad keyword file into a blog content plan and into articles that are **helpful to readers**, then check them before publishing. Reply in the language the user writes in (the team normally writes Vietnamese); **write every deliverable (brief, article, anchor, title) in English**, in the right market variant (US = American English, UK = British English).

## Fixed scope and principles

1. **Content focus.** No technical audit, no URL or sitemap work (being optimized separately, with many redirects), and no links to shop pages (`/market`, `/c`...). Links between **blog posts** are in scope.
2. **The blog leads readers to the shop naturally.** The skills do not add product links; writers leave `[PRODUCT-SLOT: ...]` placeholders that describe the context and the content team replaces them with real links. A post must **stay complete and useful with every slot removed** (`slot_check.py --strip`).
3. **Never invent.** No invented statistics, reviews, "we tested", delivery deadlines or prices. Use `[DATA NEEDED: ...]` when something is missing; tag real experience with `[EXPERIENCE: internal source]`.
4. **No mass production.** Google treats creating many pages mainly to manipulate rankings, even with AI, as *scaled content abuse*. Every post needs its own value and a human reviewer. Do not create a page for every keyword variant.
5. **Every rule states its level of evidence** (the same four levels as in the `seo-content-vn` skill): **[Google]** official guidance; **[Legal]** FTC/CMA/ASA (not legal advice); **[Research]** has data, usually correlational; **[Convention]** industry practice and heuristic thresholds. Pillar/cluster and "topical authority" are **[Convention]**; Google does not define them.

## Which skill for which situation

| The user wants | Skill | Main output |
|---|---|---|
| Read and cluster a keyword export (small to very large) on request | `keyword-clustering` | `clusters.csv`, `cluster-report.md` |
| Build pillars and clusters, see which post types are missing | `topic-map` | `topic-map.csv/.md` |
| A link plan between blog posts, or an audit of existing links | `internal-link-planner` | `link-plan.csv`, `link-audit.csv` |
| A US/UK seasonal publishing calendar | `editorial-calendar` | `occasion-calendar.csv`, `seasonal-plan.csv` |
| Briefs for writers or AI | `content-brief` | `briefs/<slug>.md` |
| The final keyword plan for the content team (one row per post, the team's 15 columns) | this skill: `scripts/export_plan.py` | `final-plan.xlsx` + `.csv` |
| All of the above in one command (keyword file -> final plan) | this skill: `scripts/run_plan.py` | the files of every step + `final-plan.xlsx` |
| Review or rewrite a post so it is helpful, honest and natural | `helpful-content-editor` | report + edits |
| Where to mention products, and the hand-off to the content team | `product-slot` | `slots.csv` |
| Check price, delivery, review, environmental and IP claims | `claims-compliance-check` | risk-flag report |

Use together with the existing skills **`seo-content-vn`** (title/meta, `seo_check.py`, GEO/AIO, images, hreflang) and **`english-grammar-style`** (mandatory when writing or editing English).

## Standard workflow

```
CSV file (SEO specialist)
  └─ keyword-clustering ──► clusters.csv + cluster-report.md   (read the report first, handle warnings, re-run if needed)
       └─ topic-map ──► topic-map.csv (pillars, clusters, priority, gaps)
            ├─ editorial-calendar ──► seasonal-plan.csv (publish dates for seasonal posts)
            ├─ internal-link-planner ──► link-plan.csv
            │    └─ export_plan.py ──► final-plan.xlsx (the content team's sheet: posts, keywords, links, planned URLs,
            │                          + Keyword Map, Schedule, QA, Research Next)
            └─ content-brief ──► briefs/*.md   (fill the [TO FILL] parts after reviewing the real SERP)
                 └─ write the post ──► helpful-content-editor + claims-compliance-check
                      └─ product-slot (hand-off) ──► content team adds links ──► publish (--final)
```

**One command** for a keyword file (runs the five steps below, prints each summary; options of a single step go through `--cluster-args`, `--topic-args`, `--export-args`):

```bash
python3 skills/printerval-blog-seo/scripts/run_plan.py export.xlsx --market us --only occasion=thanksgiving \
    --published published-posts.xlsx --previous outputs/final-plan.xlsx --out outputs
```

Step by step (run from the repository root; every script uses only the Python 3 standard library):

```bash
python3 skills/keyword-clustering/scripts/cluster_keywords.py export.csv --out outputs --group-by occasion,recipient
python3 skills/topic-map/scripts/topic_map.py outputs/clusters.csv --out outputs
python3 skills/editorial-calendar/scripts/occasion_calendar.py --topic-map outputs/topic-map.csv --out outputs
python3 skills/internal-link-planner/scripts/link_plan.py plan outputs/topic-map.csv --out outputs
python3 skills/content-brief/scripts/make_brief.py --topic-map outputs/topic-map.csv \
    --link-plan outputs/link-plan.csv --seasonal-plan outputs/seasonal-plan.csv --bucket A --out outputs/briefs
python3 skills/printerval-blog-seo/scripts/export_plan.py --topic-map outputs/topic-map.csv \
    --keyword-map outputs/keyword-map.csv --link-plan outputs/link-plan.csv \
    --seasonal-plan outputs/seasonal-plan.csv --out outputs/final-plan.xlsx
```

A one-topic Semrush export (for example `thanksgiving-day_all-keywords_us.xlsx`, broad match, so it also holds other holidays) goes in as it is: `cluster_keywords.py file.xlsx --market us --only occasion=thanksgiving`.

## The final plan (`export_plan.py`)

One row per post, in the content team's column order: `STT | Main Keyword | Secondary Keyword | Volume | KD | Category | Category Kind | Thuộc Pillar | Title SEO | Meta Description SEO | Outline | Internal Link (Anchor || URL) | Related Post (Anchor || URL) | URL Blog | Trạng thái`.

- **Left empty for the content team:** Category, Title SEO, Meta Description SEO, Outline, Trạng thái.
- **Category Kind** is Pillar or Cluster; a Cluster names its pillar in **Thuộc Pillar** (the pillar's main keyword). A group with no real pillar shows "No real pillar yet (research a head keyword)" there; no virtual pillar row is created. Rows are grouped: each pillar, then its clusters by priority.
- **Volume / KD** are the main keyword's (`--volume post` gives the post's total, an upper bound). **Secondary Keyword**: up to 10 other keywords of the post, including the clusters merged into it, largest first: at most 3 that only rephrase the main keyword (`what day is thanksgiving` next to `when is thanksgiving`), the other slots for keywords that add a new angle (`day after thanksgiving`, `is thanksgiving tomorrow`), so the list helps write the outline. No word-order/year duplicates, fixed typos, very long queries or past years (`thanksgiving bank holiday 2025` in a 2026 plan; `--year` sets the plan year).
- **Internal Link**: the body links from `link-plan.csv` (cluster -> its pillar, pillar -> every cluster, cross-pillar). **Related Post**: up to 3 siblings (for a pillar: the other pillars). Each line is `anchor || URL`.
- **URL Blog** is the planned URL, `https://printerval.com/{slug}` by default (`--url-pattern`). Printerval's CMS adds `-n<id>.html` when the post is published: paste the real URL into URL Blog and, in the `.xlsx`, every link cell that points to that post updates (they are formulas that look the URL up by STT). The `.csv` copy has plain text; `--plain-links` writes text in the `.xlsx` too.
- A second sheet, **Keyword Map**, lists every keyword placed in the plan (main, secondary, also covers, variant) with its post's STT.
- A **Schedule** sheet gives the writing order: posts whose season's usual lead time has passed first (`late: publish ASAP`, with the date it ended), then `due soon` (within 14 days), `on time` and evergreen posts; within each, priority bucket A, B, C and the priority score. Deadlines come from `--seasonal-plan` (editorial-calendar: 12 weeks before the event for a new post [Convention]); `--today` fixes the date for a reproducible run. Very hard keywords (KD >= 70) are noted as long-term targets.
- For a one-topic export, a **Research Next** sheet lists the themes a POD blog needs for that occasion (`assets/research-seeds.json`: gifts, apparel, quotes and messages, humor, decor, crafts, plus occasion ideas such as Friendsgiving) with how many keywords and searches the file has for each: `covered` only when the file holds a head keyword of the theme (`thanksgiving quotes`) and a real long tail, else `thin` or `missing` with the **seed keywords to export next** (Semrush, same market). Hand this list to the SEO specialist; do not plan posts for a theme without its keywords.
- **`--published`** (the content team's list of published blog posts: any CSV/.xlsx with a URL and a Title column; Category and a focus keyword column are used when present). A **Published Match** sheet shows, per planned post: `update this post` (a published post already answers its main question or a secondary keyword, question words aside: "When Did Thanksgiving Day Begin?" = `history of thanksgiving`): **URL Blog becomes that URL, the Schedule uses the refresh deadline, and the advice flags a stale year in the title**; `also published` (a second post answering the same question: merge them); `covers part of it` (it answers one of the merged long-tail keywords: it becomes a body link); `related live post` (it shares a subject word: listed first in Related Post, `--live-related` 1). It also lists `duplicate published posts` of the topic (same slug, another id) and posts whose title names a brand or character on `claims-compliance-check`'s IP watchlist (`IP check`; never suggested as links). Every match is a heuristic on words: a person confirms each `update this post` before the team rewrites it.
- **`--previous`** (an earlier `final-plan.xlsx`/`.csv` the team already works in, even re-saved by Excel or Google Sheets): matched posts (same URL Blog, same main keyword, or the old main keyword is now one of the post's keywords) **keep their STT, the team's columns (Category, Title SEO, Meta Description SEO, Outline, Trạng thái) and a real URL pasted in URL Blog** (every link to that post uses it); new posts get the next numbers; a previous row that matches nothing is kept as it is if the team filled anything in it, else dropped. A **Changes** sheet lists kept, renamed, new, dropped and kept-from-previous rows. Always re-run with `--previous` once the team has started on a plan.
- A **QA** sheet lists what to review before handing the plan over, most severe first: two posts asking nearly the same thing (overlap), a keyword that is another post's main question (misplaced), a year in a main keyword, duplicate or long slugs, a post absorbing 100+ clusters, posts with few internal links or none pointing to them, weak posts (< 500 searches in total) and very hard main keywords (KD >= 70). The script prints a one-line summary. **Read it and resolve or explain every high item to the user**; the others are judgment calls.

CSV schemas: `references/data-contracts.md`. Sources and verification levels: `references/sources.md`. Assumptions about Printerval and open questions: `references/printerval-context.md`.

## Working with the SEO specialist

- **Files are usually large, messy and different for every tool.** Run the script and **read `cluster-report.md` before saying anything about the result**: rows read, encoding, the tool and market detected for each file, which columns were recognised and which were ignored, excluded keywords and reasons, the unclassified share, the evidence coverage (how much of the volume is grouped by SERP data and how much by words only), warnings.
- Their requests ("group by recipient", "drop brand keywords", "US only", "volume from 200") are translated into options using the table in `keyword-clustering/SKILL.md`. State the assumptions you used. Ask only when the request is genuinely ambiguous: at most 1-2 questions, with a proposed default.
- Ask once for the **list of published blog posts** (URL + title) and use it with `--published`, so the plan updates existing posts instead of duplicating them; and keep the last `final-plan.xlsx` the team works in for `--previous`.
- The result is a **verified draft**, not the final truth: clusters built from vocabulary need Claude or the SEO to review `merge-candidates.csv` and `spelling-fixes.csv`; when SERP overlap is available (a `serp_urls` column), trust the SERP more. Hand `serp-check.csv` to the SEO (the largest word-only groupings and borderline pairs, with the question to check on the live SERP); a web search is not a Google SERP. Tool intent labels and SERP features are hints [Convention: vendor docs], not proof: a `need_source` conflict in `keyword-map.csv` is a question to settle, not a verdict.
- Do not say "done" before running the script and reading its output. Report honestly: which commands ran, the real figures, what is uncertain.

## Limits to tell the user about

- The `helpful_check.py` score and the `topic-map` priority score are **internal heuristics**, not Google metrics.
- `cluster_volume` is the sum of the keyword volumes in a cluster, so it is an upper bound (the same searchers use several phrasings).
- Seasonal lead times (12 weeks for new posts, 6 for refreshes) are an industry convention; calibrate them with the site's own GSC and Google Trends data.
- The IP/trademark list is only a starting point; high-risk claims (health, environmental, delivery, reviews) need confirmation from legal or the relevant team.
