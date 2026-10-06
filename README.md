# POWER-SEO-SKILL: SEO content skills for the Printerval blog

A suite of nine skills (for Claude Code and Claude) that helps the Printerval SEO and content team turn **very broad keyword exports** into a **blog content plan** and into articles that are **helpful to readers** (US/UK markets, English content), then check them before publishing.

Scope: **blog content**. No technical audit, no URL or sitemap work (being optimized separately), and no links to product or category pages. The content team adds product links from `[PRODUCT-SLOT]` placeholders, so the blog leads readers to the shop naturally.

## The nine skills

| Skill | What it does | Main output |
|---|---|---|
| [`printerval-blog-seo`](skills/printerval-blog-seo/SKILL.md) | Orchestration, workflow, CSV schemas, research sources | - |
| [`keyword-clustering`](skills/keyword-clustering/SKILL.md) | Reads real exports (Semrush, Ahrefs, Keyword Planner, Search Console; up to hundreds of thousands of rows), filters noise transparently, clusters and groups **on request** | `clusters.csv`, `cluster-report.md`, `groups.md` |
| [`topic-map`](skills/topic-map/SKILL.md) | Pillar/cluster structure by occasion, interest, recipient, know-how and inspiration; A/B/C priority; content gaps | `topic-map.csv/.md` |
| [`internal-link-planner`](skills/internal-link-planner/SKILL.md) | Links between blog posts, anchors, orphan posts; audit of an existing link export | `link-plan.csv`, `link-audit.csv` |
| [`editorial-calendar`](skills/editorial-calendar/SKILL.md) | US/UK holiday dates **computed by rule**, publish and refresh deadlines for seasonal posts | `seasonal-plan.csv` |
| [`content-brief`](skills/content-brief/SKILL.md) | English briefs for writers or AI, seven post formats (gift guide, how-to, and more) | `briefs/<slug>.md` |
| [`helpful-content-editor`](skills/helpful-content-editor/SKILL.md) | Reviews drafts against people-first criteria (eight-dimension rubric plus a checker script) | report, edits |
| [`product-slot`](skills/product-slot/SKILL.md) | Natural product mentions and hand-off to the content team | `slots.csv` |
| [`claims-compliance-check`](skills/claims-compliance-check/SKILL.md) | Flags delivery, review, environmental, health and price claims and IP names (FTC/CMA/ASA) | report |

## Workflow

```
CSV from the SEO specialist
  -> keyword-clustering -> clusters.csv + cluster-report.md   (read the report first)
    -> topic-map -> topic-map.csv
        |- editorial-calendar -> seasonal-plan.csv
        |- internal-link-planner -> link-plan.csv
        '- content-brief -> briefs/*.md -> write the article
              -> helpful-content-editor + claims-compliance-check
              -> product-slot (content team adds the links) -> publish
```

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

# 3. Check a draft
python3 skills/helpful-content-editor/scripts/helpful_check.py draft.md --market us --post-type gift-guide --keyword "mother's day gifts for grandma"
python3 skills/product-slot/scripts/slot_check.py draft.md --post-type gift-guide --export slots.csv
python3 skills/claims-compliance-check/scripts/claims_check.py draft.md --market us
```

`examples/` contains **synthetic** data (not real figures) and two sample drafts (`draft-weak-demo.md` has deliberate flaws, `draft-good-demo.md` is a passing example) to try the tools on.

## Clustering "on request"

SEO specialists describe what they need in plain words; the skill turns that into options (the full table is in [`keyword-clustering/SKILL.md`](skills/keyword-clustering/SKILL.md)):

| Request | Option |
|---|---|
| Group by recipient, occasion, interest, product or reader intent | `--group-by recipient` (`occasion`, `interest`, `product`, `intent`, ...) |
| Custom groups (Family, Pets, Work, ...) | `--categories categories.json --group-by category` |
| Only some occasions, drop terms, limit volume or difficulty | `--only occasion=mothers-day`, `--exclude "\bfree\b"`, `--min-volume 100`, `--max-kd 60` |
| Finer or broader clusters | `--granularity tight` / `loose` |
| US and UK | `us.csv::us uk.csv::uk`, or a Country column |
| New niches | `--extend-taxonomy extra.json` (suggestions are written to `taxonomy-suggestions.csv`) |

The script handles UTF-16/tab files (Keyword Planner), description lines above the header, `, ; tab |` delimiters and numbers such as `1K - 10K` or `1.234`. It drops noisy keywords (retailers, "near me", Spanish, and similar) **with a reason for each** in `excluded.csv`. 150,000 keywords take about a minute.

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

77 tests: multi-format file reading, facet detection, clustering (checked against pairwise comparison), filters, topic map, link plan and audit, holiday dates checked against the real calendar, briefs and the three checkers.

## Layout

```
skills/<skill>/SKILL.md, scripts/, references/, assets/   # each skill is self-contained
examples/   synthetic data, sample request/categories/taxonomy files, demo drafts
tests/      unit tests and a large-data generator
docs/       research-notes.md
scripts/    package_skills.py
```

## Maintenance

- **Taxonomy** (`skills/keyword-clustering/assets/taxonomy.json`): add niches and occasions when `taxonomy-suggestions.csv` shows unclassified keywords.
- **Noise rules** (`assets/noise-rules.json`) and the **IP list** (`claims-compliance-check/assets/ip-watchlist.txt`, only a starting sample; legal should maintain the real list).
- **Calendar** (`occasion_calendar.py`, `OCCASIONS`): add new occasions together with a test against the real date.
- Guidance from Google, the FTC, the CMA and the ASA changes: update `references/sources.md` and re-check the original pages.
