# POWER-SEO-SKILL: SEO content skills for the Printerval blog

A suite of nine skills (for Claude Code and Claude) that helps the Printerval SEO and content team turn **very broad keyword exports** into a **blog content plan** and into articles that are **helpful to readers** (US/UK markets, English content), then check them before publishing.

Scope: **blog content**. No technical audit, no URL or sitemap work (being optimized separately), and no links to product or category pages. The content team adds product links from `[PRODUCT-SLOT]` placeholders, so the blog leads readers to the shop naturally.

## The nine skills

| Skill | What it does | Main output |
|---|---|---|
| [`printerval-blog-seo`](skills/printerval-blog-seo/SKILL.md) | Orchestration, workflow, CSV schemas, research sources; **the final plan for the content team** | `final-plan.xlsx` |
| [`keyword-clustering`](skills/keyword-clustering/SKILL.md) | Reads real exports (CSV or Excel from Semrush, Ahrefs, Keyword Planner, Search Console; up to hundreds of thousands of rows), fixes typos, filters noise transparently, merges question variants into one post, clusters and groups **on request** | `clusters.csv`, `cluster-report.md`, `groups.md` |
| [`topic-map`](skills/topic-map/SKILL.md) | Pillar/cluster structure by occasion, interest, recipient, know-how and inspiration; splits a one-topic export into theme pillars and merges small clusters into the closest post; A/B/C priority; content gaps | `topic-map.csv/.md` |
| [`internal-link-planner`](skills/internal-link-planner/SKILL.md) | Links between blog posts, anchors, orphan posts; audit of an existing link export | `link-plan.csv`, `link-audit.csv` |
| [`editorial-calendar`](skills/editorial-calendar/SKILL.md) | US/UK holiday dates **computed by rule**, publish and refresh deadlines for seasonal posts | `seasonal-plan.csv` |
| [`content-brief`](skills/content-brief/SKILL.md) | English briefs for writers or AI, seven post formats (gift guide, how-to, and more) | `briefs/<slug>.md` |
| [`helpful-content-editor`](skills/helpful-content-editor/SKILL.md) | Reviews drafts against people-first criteria (eight-dimension rubric plus a checker script) | report, edits |
| [`product-slot`](skills/product-slot/SKILL.md) | Natural product mentions and hand-off to the content team | `slots.csv` |
| [`claims-compliance-check`](skills/claims-compliance-check/SKILL.md) | Flags delivery, review, environmental, health and price claims and IP names (FTC/CMA/ASA) | report |

## Workflow

```
Raw export and/or a file the SEO already grouped (--prior)
  -> keyword-clustering -> clusters.csv + cluster-report.md + backcheck.csv   (read the reports first)
    -> topic-map -> topic-map.csv
        |- editorial-calendar -> seasonal-plan.csv
        |- internal-link-planner -> link-plan.csv
        |    '- export_plan.py -> final-plan.xlsx   (the content team's sheet + schedule, QA, research next,
        |                                            review, back-check, decisions, not planned)
        '- content-brief -> briefs/*.md -> write the article
              -> helpful-content-editor + claims-compliance-check
              -> product-slot (content team adds the links) -> publish
```

Three kinds of input go through one command, `skills/printerval-blog-seo/scripts/run_plan.py`: a raw export (`run_plan.py export.xlsx --market us --out outputs`), a file the SEO already grouped (`--prior grouped.xlsx::us`; its groups are audited against the same rules and regrouped only where a rule fails, every change and its reason in the SEO Audit sheet; `--prior-mode keep` keeps them as they are), or both (the export back-fills volume, KD, intent and SERP features and supplements missing keywords). Judgment calls go into a decisions file (`--decisions decisions.csv`), each with a reason and evidence; the scripts apply them deterministically, reject a Claude decision the SERP data contradicts and log every one in the final file. Claude reviews in two passes (structure, then content): see `skills/printerval-blog-seo/SKILL.md` and `skills/keyword-clustering/references/backcheck-and-decisions.md`.

## Quick start (Python 3, standard library only; tested on 3.13)

```bash
# 1. Cluster on request: group by occasion then recipient, US only, drop keywords under 100 searches
python3 skills/keyword-clustering/scripts/cluster_keywords.py examples/synthetic-keywords-us.csv \
    --out outputs --market us --min-volume 100 --group-by occasion,recipient

# or save the request in a file and re-run it
python3 skills/keyword-clustering/scripts/cluster_keywords.py --request examples/request-example.json

# 2. Pillar/cluster map, seasonal calendar, link plan, briefs for the priority-A posts
python3 skills/topic-map/scripts/topic_map.py outputs/clusters.csv --out outputs
python3 skills/editorial-calendar/scripts/occasion_calendar.py --topic-map outputs/topic-map.csv --out outputs
python3 skills/internal-link-planner/scripts/link_plan.py plan outputs/topic-map.csv --out outputs
python3 skills/content-brief/scripts/make_brief.py --topic-map outputs/topic-map.csv \
    --link-plan outputs/link-plan.csv --seasonal-plan outputs/seasonal-plan.csv --bucket A --out outputs/briefs

# 3. The final plan for the content team (one row per post, 15 columns, .xlsx + .csv)
#    (or steps 1-3 in one command: skills/printerval-blog-seo/scripts/run_plan.py export.xlsx --market us --out outputs)
python3 skills/printerval-blog-seo/scripts/export_plan.py --topic-map outputs/topic-map.csv \
    --keyword-map outputs/keyword-map.csv --link-plan outputs/link-plan.csv \
    --seasonal-plan outputs/seasonal-plan.csv --out outputs/final-plan.xlsx

# 4. Check a draft
python3 skills/helpful-content-editor/scripts/helpful_check.py draft.md --market us --post-type gift-guide --keyword "mother's day gifts for grandma"
python3 skills/product-slot/scripts/slot_check.py draft.md --post-type gift-guide --export slots.csv
python3 skills/claims-compliance-check/scripts/claims_check.py draft.md --market us
```

`examples/` contains **synthetic** data (not real figures) and two sample drafts (`draft-weak-demo.md` has deliberate flaws, `draft-good-demo.md` is a passing example) to try the tools on.

### A one-topic Semrush export (for example "thanksgiving day", all keywords)

```bash
python3 skills/keyword-clustering/scripts/cluster_keywords.py thanksgiving-day_all-keywords_us.xlsx --market us \
    --only occasion=thanksgiving --out outputs
```

Semrush's "all keywords" is broad match, so the file also holds other holidays; `--only` keeps the topic (typos such as `thanksgivng` are fixed first, so they are kept). The questions are merged into posts (`when is thanksgiving` = `what day is thanksgiving 2026`) and topic-map splits the topic into theme pillars (Dates & Calendar, History & Origins, Meaning, Facts & Trivia, Traditions & Activities, Quotes & Messages, Around the World). On a real 30,000-row export this gave 7 pillars and about 35 posts, with every other cluster merged into the closest post as secondary keywords.

### The final plan (`final-plan.xlsx`)

`STT | Main Keyword | Secondary Keyword | Volume | KD | Category | Category Kind | Thuộc Pillar | Title SEO | Meta Description SEO | Outline | Internal Link (Anchor || URL) | Related Post (Anchor || URL) | URL Blog | Trạng thái`

Category, Title SEO, Meta Description SEO, Outline and Trạng thái are left for the content team. Category Kind is Pillar or Cluster, and a Cluster names its pillar. URL Blog is the planned URL (`https://printerval.com/{slug}`, change it with `--url-pattern`); the link cells in the .xlsx look the target's URL Blog up, so pasting the real URL after publishing updates every link to that post. With the team's list of published posts (`--published`, URL + Title), a post that already exists keeps its real URL and becomes an update, related live posts are suggested as links, and duplicate or IP-sensitive published posts are listed. With the plan the team already works in (`--previous`), every post keeps its STT, the team's columns and the real URLs pasted after publishing. Main keywords, pillars and the priority order follow the traffic the blog can win (volume x fit of the KD against the site's reach, `--site-kd`), not raw volume. Internal links are planned as a structure: every post links up to its pillar (and its sub-hub), a pillar links to its sub-hubs and its most valuable posts (at most 12), plus up to 2 contextual links per post with the reason and the place in the post (sheet Link Plan). Other sheets: Keyword Map (where every keyword went), SEO Audit (with `--prior`: what the rules changed in the SEO's grouping, group by group), Schedule (writing order: deadlines that can still be met first, then posts late for their season, then by priority), QA (what to check before handing the plan over: overlapping posts, misplaced keywords, orphans, weak posts) and, for a one-topic export, Research Next (themes such as gifts, shirts, quotes or decor that the file barely covers, with the seed keywords to export next).

## Clustering "on request"

SEO specialists describe what they need in plain words; the skill turns that into options (the full table is in [`keyword-clustering/SKILL.md`](skills/keyword-clustering/SKILL.md)):

| Request | Option |
|---|---|
| Group by recipient, occasion, interest, product or reader intent | `--group-by recipient` (`occasion`, `interest`, `product`, `intent`, ...) |
| Custom groups (Family, Pets, Work, ...) | `--categories categories.json --group-by category` |
| Only some occasions, drop terms, limit volume or difficulty | `--only occasion=mothers-day`, `--exclude "\bfree\b"`, `--min-volume 100`, `--max-kd 60` |
| Finer or broader clusters | `--granularity tight` / `loose` |
| By sub-topic (dates, history, quotes...) | `--group-by theme`, `--only theme=history` |
| US and UK | `us.csv::us uk.csv::uk`, or a Country column |
| New niches | `--extend-taxonomy extra.json` (suggestions are written to `taxonomy-suggestions.csv`) |

The script reads Excel files (every sheet) and UTF-16/tab files (Keyword Planner), description lines above the header, `, ; tab |` delimiters, cells with several lines, and numbers such as `1K - 10K` or `1.234`. It keeps the evidence the tools export (intent, SERP features, Semrush Trend, Ahrefs SV trend and Traffic potential, Keyword Planner monthly searches, the ranking URL), names the tool and the market of each file, counts a keyword found in two files once, and says in `cluster-report.md` how much of the grouping rests on SERP data; `serp-check.csv` lists the groupings to check on the live SERP and `spelling-fixes.csv` every spelling correction. It fixes typos learned from the file itself and drops noisy keywords (retailers, "near me", Spanish, politics, homework answer keys, opening hours, TV shows, restaurant menus, school calendars, and similar) **with a reason for each** in `excluded.csv`. 150,000 keywords take about 85 seconds.

## Content principles

1. **The post is still useful with every product removed.** Products appear as the answer to the reader's problem.
2. **Original value**: real Printerval experience and data (`[EXPERIENCE]`, `[DATA]`), not commodity content. Never invent experience, statistics, reviews, delivery deadlines or prices.
3. **No mass production**: one cluster is one post, reviewed by a person (Google's scaled content abuse policy).
4. **Honest claims**: delivery, review, environmental, health and price claims and IP names are flagged for people or legal to decide (this is not legal advice).

Every rule in the documentation carries an evidence level: **[Google]**, **[Legal]**, **[Research]** or **[Convention]**. Research notes and the verification level of each source: [`docs/research-notes.md`](docs/research-notes.md) and [`skills/printerval-blog-seo/references/sources.md`](skills/printerval-blog-seo/references/sources.md).

## Installing the skills

Use **all nine together**: `printerval-blog-seo` is the entry point and the skills hand CSV files to each other.

- **Claude Code (recommended for the team):** clone the repository and open the folder. `.claude/skills` is a symlink to `skills/`, so the skills load automatically. A ZIP download may not keep the symlink on Windows; in that case run `python3 scripts/package_skills.py --install ~/.claude/skills`.
- **claude.ai or the Claude app:** upload one zip per skill (nine uploads). `python3 scripts/package_skills.py` builds `dist/<skill>.zip`. Make sure Skills and code execution are enabled in Settings so the Python scripts can run. When `topic-map` is uploaded on its own it derives pillar names from keys instead of reading the taxonomy labels; it still works.
- Use alongside the existing skills **`seo-content-vn`** (title and meta, GEO/AIO, images, hreflang) and **`english-grammar-style`**.

The skill instructions, reference documents and deliverables (briefs, articles, anchors, titles) are all in English. Claude replies in the language the user writes in (the team normally writes Vietnamese).

## Tests

```bash
python3 -W error::ResourceWarning -m unittest discover -s tests
python3 tests/make_big_fixture.py 150000 /tmp/big.csv   # performance check
```

236 tests: multi-format file reading (including .xlsx with every sheet, multi-line cells and fixtures built on real Semrush, Ahrefs, Keyword Planner and Search Console headers), evidence parsing (intent, SERP features, trend, Keyword Planner buckets), joining the same keyword from several files, spelling fixes (typos, split, glued and cut-off words), facet and theme detection, clustering (checked against pairwise comparison) and question consolidation, natural post names, filters, topic map with theme pillars, sub-topic posts and merged posts, link plan and audit, contextual links, the final plan export (secondary keywords, schedule, QA and research sheets, published posts, re-runs on a previous plan), the one-command pipeline, the SEO's grouped file (every layout, including one keyword per row below its main) audited against the rules and regrouped only on evidence (same query, duplicates, shopping keywords, a better main keyword, pillar fit and hub, sections for small groups) or kept as it is, keyword difficulty against the site's reach (winnable volume, Personal KD), sub-hubs and the planned internal links with a budget and a reason per link, the back-check of every group with a proposed decision per issue, the decisions file applied by the cluster, topic and export steps with a log per decision, the Review, Back-check, Decisions and Not Planned sheets, holiday dates checked against the real calendar, briefs and the three checkers.

## Layout

```
skills/<skill>/SKILL.md, scripts/, references/, assets/   # each skill is self-contained
examples/   synthetic data, sample request/categories/taxonomy files, demo drafts
tests/      unit tests and a large-data generator
docs/       research-notes.md
scripts/    package_skills.py
```

## Maintenance

- **Taxonomy** (`skills/keyword-clustering/assets/taxonomy.json`): add niches and occasions when `taxonomy-suggestions.csv` shows unclassified keywords; add theme patterns or `core_synonyms` when two phrasings of one question still land in two posts.
- **Noise rules** (`assets/noise-rules.json`) and the **IP list** (`claims-compliance-check/assets/ip-watchlist.txt`, only a starting sample; legal should maintain the real list).
- **Calendar** (`occasion_calendar.py`, `OCCASIONS`): add new occasions together with a test against the real date.
- Guidance from Google, the FTC, the CMA and the ASA changes: update `references/sources.md` and re-check the original pages.
