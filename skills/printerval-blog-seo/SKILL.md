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
Raw export and/or grouped file (SEO specialist)
  └─ keyword-clustering ──► clusters.csv, keyword-map.csv, cluster-report.md, backcheck.csv + proposed-decisions.csv
       │                    (read the reports first; decisions.csv ──► decisions-log-cluster.csv)
       └─ topic-map ──► topic-map.csv (pillars, clusters, priority, gaps; decisions ──► decisions-log-topic.csv)
            ├─ editorial-calendar ──► seasonal-plan.csv (publish dates for seasonal posts)
            ├─ internal-link-planner ──► link-plan.csv
            │    └─ export_plan.py ──► final-plan.xlsx (the content team's 15 columns, + Keyword Map, Schedule, QA,
            │                          SEO Audit, Link Plan, Research Next, Review, Back-check, Decisions, Not Planned)
            └─ content-brief ──► briefs/*.md   (fill the [TO FILL] parts after reviewing the real SERP)
                 └─ write the post ──► helpful-content-editor + claims-compliance-check
                      └─ product-slot (hand-off) ──► content team adds links ──► publish (--final)
```

### Three kinds of input, one pipeline

| The SEO sends | Run |
|---|---|
| A raw export (Semrush, Ahrefs, Keyword Planner, GSC) | `run_plan.py export.xlsx --market us --out outputs` |
| A file they already grouped (keyword + group columns, main + secondary keyword columns, or the team's earlier final plan with its Keyword Map sheet) | `run_plan.py --prior grouped.xlsx::us --out outputs` |
| Both | `run_plan.py export.xlsx --prior grouped.xlsx::us --out outputs` (the export back-fills volume, KD, intent, trend and SERP features, and supplements keywords the grouping missed) |

A grouped file goes in **only through `--prior`** (a positional file is always read as a raw export). It is the starting point, and the skill's job is to make it the best content plan: **by default (`--prior-mode audit`) every group is checked against the same rules as a raw export and regrouped where a rule fails, never silently**: every change (same query in two groups merged, a keyword listed twice placed once, a shopping keyword split out, a better main keyword, a post moved to the pillar it belongs to, a broader pillar the site can win, two groups that ask the same thing, a group too small for its own page made a section of the closest post) is a row of the **SEO Audit** sheet with its reason and its STT in the plan; a group no rule finds anything against stays as the SEO set it ("kept"). Word similarity alone never splits an SEO group, and a duplicate the words only suggest is listed for a SERP check, not applied. `--prior-mode keep` keeps the SEO's groups and pillars exactly (`prior:seo`). `--site-kd N` tells the skill what keyword difficulty the site can rank for (else measured from a positions export, else 30): main keywords, pillars and the priority order then follow the **winnable volume** (volume x fit of the KD), so a high-volume keyword the blog cannot rank for no longer heads a pillar, and a competitor's secondary keyword with a lower KD can be our main keyword. Every group is also back-checked against the data (`backcheck.csv`) with a proposed decision per issue; a decisions file changes the rest. After the review, re-run with `--decisions decisions.csv`: `run_plan.py` passes it to the cluster step, `topic_map.py` and `export_plan.py`, and hands `backcheck.csv`, `excluded.csv` and every `decisions-log-*.csv` to `export_plan.py`.

```bash
python3 skills/printerval-blog-seo/scripts/run_plan.py export.xlsx --prior grouped.xlsx::us --market us \
    --decisions decisions.csv --published published-posts.xlsx --previous outputs/final-plan.xlsx --out outputs
```

Options of a single step go through `--cluster-args`, `--topic-args`, `--export-args`. Step by step (run from the repository root; every script uses only the Python 3 standard library):

```bash
python3 skills/keyword-clustering/scripts/cluster_keywords.py export.csv --prior grouped.xlsx::us \
    --decisions decisions.csv --out outputs --group-by occasion,recipient
python3 skills/topic-map/scripts/topic_map.py outputs/clusters.csv --decisions decisions.csv --out outputs
python3 skills/editorial-calendar/scripts/occasion_calendar.py --topic-map outputs/topic-map.csv --out outputs
python3 skills/internal-link-planner/scripts/link_plan.py plan outputs/topic-map.csv --out outputs
python3 skills/content-brief/scripts/make_brief.py --topic-map outputs/topic-map.csv \
    --link-plan outputs/link-plan.csv --seasonal-plan outputs/seasonal-plan.csv --bucket A --out outputs/briefs
python3 skills/printerval-blog-seo/scripts/export_plan.py --topic-map outputs/topic-map.csv \
    --keyword-map outputs/keyword-map.csv --link-plan outputs/link-plan.csv \
    --seasonal-plan outputs/seasonal-plan.csv --decisions decisions.csv --backcheck outputs/backcheck.csv \
    --excluded outputs/excluded.csv --decision-log outputs/decisions-log-cluster.csv \
    --decision-log outputs/decisions-log-topic.csv --out outputs/final-plan.xlsx
```

A one-topic Semrush export (for example `thanksgiving-day_all-keywords_us.xlsx`, broad match, so it also holds other holidays) goes in as it is: `cluster_keywords.py file.xlsx --market us --only occasion=thanksgiving`.

### The review step (Claude), the core of the method

The scripts compute evidence; Claude (or the SEO) makes the judgment calls in `decisions.csv`; the scripts apply them deterministically on every re-run and log them in the final file. Run at least two passes. Formats, checks, actions per step and the contradiction rule: `keyword-clustering/references/backcheck-and-decisions.md`.

**Pass 1: structure.** After the first run, read in this order: `cluster-report.md` (input, recognised and ignored columns, evidence coverage, warnings), `backcheck-report.md`, then `backcheck.csv` sorted by severity and volume, `spelling-fixes.csv`, `excluded.csv` (by volume), `merge-candidates.csv`. For each high issue, and each medium issue among the 30 largest groups by volume [Convention: review budget], accept, edit or reject the matching row of `proposed-decisions.csv` and write the accepted ones to `decisions.csv` with `author=claude`, a `reason` and the `evidence`. Everything else stays `open` and is labelled as a heuristic default in the final file.

**Pass 2: content.** Re-run with `--decisions decisions.csv`. Check the Decisions sheet: every decision is `applied`, or its `stale`/`invalid`/`rejected_by_data`/`conflict` status is fixed or explained to the user. Then, in the Review sheet, write one `set_angle` per post (the reader need it serves for Printerval's audience, US/UK buyers of print-on-demand gifts and apparel, and which interpretation of the query it targets). Write `set_outline` for the rows the user asked for (default: bucket A), built from Outline Seeds. Write `drop_post` with reason `off-audience` when no honest angle exists. Re-run.

**Before writing any decision, check and write down:**
1. **Evidence, quoted from the files:** the `issue_id` and the numbers (volumes, SERP overlap counts, Parent Topic, the Semrush/Ahrefs intent labels, SERP features, trend peak). Never write a number that is not in a file. Your web search is not a Google SERP: never record overlap counts from it.
2. **The evidence hierarchy:** SERP overlap > Parent Topic or KSB Page > co-ranking URL > tool intent and SERP features > monthly data > word similarity > your reading of the meaning. A decision that rests only on the last two says "not verified by SERP" in `evidence`, and the pair goes to the SEO through `serp-check.csv`. [Convention: vendor docs; thresholds disagree between tools]
3. **Merge rule [Google]:** same SERP and compatible intent means one post (site diversity; doorway and scaled-content policies). Keeping two close variants apart needs SERP evidence that they differ, and a stated angle for each.
4. **Data beats you:** a `claude` decision contradicted by SERP or Parent Topic data is `rejected_by_data` by the script. Do not retry it; tell the user, and ask the SEO to check the live SERP. A human decision against the data is `applied_with_warning`.
5. **Nothing invented:** decisions only move, merge, split, rename, keep or drop keywords that are in the data. A brainstormed topic the file does not cover becomes a `research_seed` (Research Next, unverified until exported), never a post. Outlines contain no invented facts, figures, experience or word counts; mark gaps `[DATA NEEDED: ...]`; never promise FAQ or HowTo rich results [Google].
6. **US and UK** are never merged; UK wording in UK rows.
7. **Pillars are a [Convention]:** promote a pillar only when the head term has a broad SERP or the data shows at least two distinct sub-topics under it; never claim "topical authority".

**Report to the user** (in their language): what was read, how many groups were confirmed by SERP / kept unverified / changed, the decisions applied with their basis, what still needs the SEO (the `serp-check.csv` list, `[DATA NEEDED]` rows), and where each is in the final file (Review, Back-check, Decisions, Not Planned sheets).

## The final plan (`export_plan.py`)

One row per post, in the content team's column order: `STT | Main Keyword | Secondary Keyword | Volume | KD | Category | Category Kind | Thuộc Pillar | Title SEO | Meta Description SEO | Outline | Internal Link (Anchor || URL) | Related Post (Anchor || URL) | URL Blog | Trạng thái`.

- **Left empty for the content team:** Category, Title SEO, Meta Description SEO, Outline, Trạng thái.
- **Category Kind** is Pillar or Cluster; a Cluster names its pillar in **Thuộc Pillar** (the pillar's main keyword). A group with no real pillar shows "No real pillar yet (research a head keyword)" there; no virtual pillar row is created. Rows are grouped: each pillar, then its clusters by priority.
- **Volume / KD** are the main keyword's (`--volume post` gives the post's total, an upper bound). **Secondary Keyword**: up to 10 other keywords of the post, including the clusters merged into it, largest first: at most 3 that only rephrase the main keyword (`what day is thanksgiving` next to `when is thanksgiving`), the other slots for keywords that add a new angle (`day after thanksgiving`, `is thanksgiving tomorrow`), so the list helps write the outline. No word-order/year duplicates, fixed typos, very long queries or past years (`thanksgiving bank holiday 2025` in a 2026 plan; `--year` sets the plan year).
- **Internal Link**: the body links from `link-plan.csv`, planned as a structure (internal-link-planner): every post -> its pillar (and its sub-hub), a pillar -> its sub-hubs and its most valuable posts (at most 12), a sub-hub -> its posts, up to 2 contextual links to the posts that talk about the same thing (more toward posts whose keyword is still above the site's reach), cross-pillar at most once. **Related Post**: up to 3 posts of the same sub-hub or pillar for the related-reading block (for a pillar: the other pillars). Each line is `anchor || URL`; every anchor describes its target (no other number, no inverted phrasing). The **Link Plan** sheet lists every link with its type, placement in the post and reason.
- **URL Blog** is the planned URL, `https://printerval.com/{slug}` by default (`--url-pattern`). Printerval's CMS adds `-n<id>.html` when the post is published: paste the real URL into URL Blog and, in the `.xlsx`, every link cell that points to that post updates (they are formulas that look the URL up by STT). The `.csv` copy has plain text; `--plain-links` writes text in the `.xlsx` too.
- A second sheet, **Keyword Map**, lists every keyword placed in the plan (main, secondary, also covers, variant) with its post's STT.
- A **Schedule** sheet gives the writing order: posts whose season's usual lead time has passed first (`late: publish ASAP`, with the date it ended), then `due soon` (within 14 days), `on time` and evergreen posts; within each, priority bucket A, B, C and the priority score. Deadlines come from `--seasonal-plan` (editorial-calendar: 12 weeks before the event for a new post [Convention]); `--today` fixes the date for a reproducible run. Very hard keywords (KD >= 70) are noted as long-term targets.
- For a one-topic export, a **Research Next** sheet lists the themes a POD blog needs for that occasion (`assets/research-seeds.json`: gifts, apparel, quotes and messages, humor, decor, crafts, plus occasion ideas such as Friendsgiving) with how many keywords and searches the file has for each: `covered` only when the file holds a head keyword of the theme (`thanksgiving quotes`) and a real long tail, else `thin` or `missing` with the **seed keywords to export next** (Semrush, same market). Hand this list to the SEO specialist; do not plan posts for a theme without its keywords.
- **`--published`** (the content team's list of published blog posts: any CSV/.xlsx with a URL and a Title column; Category and a focus keyword column are used when present). A **Published Match** sheet shows, per planned post: `update this post` (a published post already answers its main question or a secondary keyword, question words aside: "When Did Thanksgiving Day Begin?" = `history of thanksgiving`): **URL Blog becomes that URL, the Schedule uses the refresh deadline, and the advice flags a stale year in the title**; `also published` (a second post answering the same question: merge them); `covers part of it` (it answers one of the merged long-tail keywords: it becomes a body link); `related live post` (it shares a subject word: listed first in Related Post, `--live-related` 1). It also lists `duplicate published posts` of the topic (same slug, another id) and posts whose title names a brand or character on `claims-compliance-check`'s IP watchlist (`IP check`; never suggested as links). Every match is a heuristic on words: a person confirms each `update this post` before the team rewrites it.
- **`--previous`** (an earlier `final-plan.xlsx`/`.csv` the team already works in, even re-saved by Excel or Google Sheets): matched posts (same URL Blog, same main keyword, or the old main keyword is now one of the post's keywords) **keep their STT, the team's columns (Category, Title SEO, Meta Description SEO, Outline, Trạng thái) and a real URL pasted in URL Blog** (every link to that post uses it); new posts get the next numbers; a previous row that matches nothing is kept as it is if the team filled anything in it, else dropped. A **Changes** sheet lists kept, renamed, new, dropped and kept-from-previous rows. Always re-run with `--previous` once the team has started on a plan.
- **SEO Audit** (with `--prior`, from `seo-audit.csv` and `seo-audit-topic.csv`): one or more rows per SEO group in the SEO's own order (STT): what the rules changed or `kept`, the keyword, its volume, where it is now (STT and main keyword) and why, with the evidence level. **Link Plan**: every planned link (from STT, to STT, type, anchor, placement, priority, reason).
- After the existing sheets, four sheets show what each row rests on (`scripts/plan_review.py`; values come only from the data, nothing is invented): **Review** (one row per STT: tool intent and whether it fits the reader need, the main keyword's SERP features, the grouping basis, the SEO's group, main and owned volume, KD, outline seeds taken from the post's own keywords with their real volumes, the reviewed angle or `unreviewed`, open back-check issues, decisions applied, and why the post exists in numbers); **Back-check** (`--backcheck`: `backcheck.csv` as it is, status updated from the decision logs); **Decisions** (`--decision-log`, repeatable: every logged decision with its status, plus the reason and evidence from the decisions file); **Not Planned** (backlog and skip clusters and the biggest keywords the noise filters excluded, `--not-planned-max` 300: where each went, the reason and the nearest planned post; keywords outside the run's scope such as `--only` are one summary row, and clusters merged into a post are planned as sections, listed in Keyword Map). Without those files only Review and Not Planned appear. Keyword Map stays the second sheet.
- Category, Title SEO, Meta Description SEO and Outline are filled only by the team or by a reviewed decision (`set_category`, `set_title`, `set_meta`, `set_outline`); a team value always wins (`team_value_kept`). A cell a decision wrote on the previous run (`--previous`, its Decisions sheet) belongs to that decision: a changed value replaces it and a decision removed from the file clears it (`withdrawn`).
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
