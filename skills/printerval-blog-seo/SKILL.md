---
name: printerval-blog-seo
description: Orchestrates the Printerval blog SEO skill suite (print-on-demand marketplace, US and UK markets, English content). Use when the user talks about the Printerval blog, keyword export CSV files from SEO specialists (Semrush, Ahrefs, Keyword Planner, Search Console), keyword clustering, pillar and cluster planning, topic maps, internal links between blog posts, content briefs, gift guides, seasonal content calendars (Mother's Day, Christmas), product slots, claim and IP checks, or whether a draft is helpful to readers. Not for technical audits, URLs or sitemaps, or links to product pages.
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
            └─ content-brief ──► briefs/*.md   (fill the [TO FILL] parts after reviewing the real SERP)
                 └─ write the post ──► helpful-content-editor + claims-compliance-check
                      └─ product-slot (hand-off) ──► content team adds links ──► publish (--final)
```

Sample commands (run from the repository root; every script uses only the Python 3 standard library):

```bash
python3 skills/keyword-clustering/scripts/cluster_keywords.py export.csv --out outputs --group-by occasion,recipient
python3 skills/topic-map/scripts/topic_map.py outputs/clusters.csv --out outputs
python3 skills/editorial-calendar/scripts/occasion_calendar.py --topic-map outputs/topic-map.csv --out outputs
python3 skills/internal-link-planner/scripts/link_plan.py plan outputs/topic-map.csv --out outputs
python3 skills/content-brief/scripts/make_brief.py --topic-map outputs/topic-map.csv \
    --link-plan outputs/link-plan.csv --seasonal-plan outputs/seasonal-plan.csv --bucket A --out outputs/briefs
```

CSV schemas: `references/data-contracts.md`. Sources and verification levels: `references/sources.md`. Assumptions about Printerval and open questions: `references/printerval-context.md`.

## Working with the SEO specialist

- **Files are usually large, messy and different for every tool.** Run the script and **read `cluster-report.md` before saying anything about the result**: rows read, encoding, which columns were recognised, excluded keywords and reasons, the unclassified share, warnings.
- Their requests ("group by recipient", "drop brand keywords", "US only", "volume from 200") are translated into options using the table in `keyword-clustering/SKILL.md`. State the assumptions you used. Ask only when the request is genuinely ambiguous: at most 1-2 questions, with a proposed default.
- The result is a **verified draft**, not the final truth: clusters built from vocabulary need Claude or the SEO to review `merge-candidates.csv`; when SERP overlap is available (a `serp_urls` column), trust the SERP more.
- Do not say "done" before running the script and reading its output. Report honestly: which commands ran, the real figures, what is uncertain.

## Limits to tell the user about

- The `helpful_check.py` score and the `topic-map` priority score are **internal heuristics**, not Google metrics.
- `cluster_volume` is the sum of the keyword volumes in a cluster, so it is an upper bound (the same searchers use several phrasings).
- Seasonal lead times (12 weeks for new posts, 6 for refreshes) are an industry convention; calibrate them with the site's own GSC and Google Trends data.
- The IP/trademark list is only a starting point; high-risk claims (health, environmental, delivery, reviews) need confirmation from legal or the relevant team.
