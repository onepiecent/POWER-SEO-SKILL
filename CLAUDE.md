# CLAUDE.md

This repo is an SEO content skill set for the **Printerval blog** (print-on-demand, US/UK markets). Read `README.md` first, then `skills/printerval-blog-seo/SKILL.md` (the orchestrator).

## Working conventions

- Reply in the user's language (the current maintainers write in Vietnamese); every deliverable (briefs, posts, anchors, titles) is in **English**, in the correct US or UK variant.
- The scope is **blog content**. No technical audit, no URLs/sitemap, no links to shop pages (the content team adds them through `[PRODUCT-SLOT]`).
- Never invent figures, reviews, experience, delivery deadlines or prices. If something is missing, write `[DATA NEEDED: ...]`.
- Every rule states its level of evidence: **[Google]**, **[Legal]** (not legal advice), **[Research]**, **[Convention]**. Scores and thresholds in the scripts are internal heuristics.
- The SEO specialists' CSV files can be large and dirty: always run the script and read `cluster-report.md` before reporting results.

## Commands

```bash
python3 -W error::ResourceWarning -m unittest discover -s tests     # 125 tests, runs in a few seconds
python3 scripts/package_skills.py                                    # dist/<skill>.zip
python3 skills/printerval-blog-seo/scripts/export_plan.py --help     # final plan (.xlsx) for the content team
python3 skills/printerval-blog-seo/scripts/run_plan.py --help        # the whole pipeline in one command
```

The scripts use only the Python 3 standard library (tested on 3.13). Each skill is self-contained in `skills/<name>/` (SKILL.md, scripts/, references/, assets/); do not import across skills. Two data files are read across skills, each with a fallback when missing: `topic-map` reads `keyword-clustering`'s `taxonomy.json` to name pillars, and `printerval-blog-seo/scripts/published.py` reads `claims-compliance-check`'s `ip-watchlist.txt` to flag published posts that name a brand. `run_plan.py` runs the other skills' scripts as separate processes (no import).

## When editing

- Adding or changing taxonomy regexes, themes, core synonyms or noise rules: run the tests; re-read `excluded.csv` and `topic-map.md` on sample data (a theme regex decides which pillar a post lands in).
- Adding an occasion: edit `OCCASIONS` in `occasion_calendar.py` and add a test that checks the date against the **real calendar** (do not take dates from search results, which have been wrong before).
- The SKILL.md frontmatter must be valid YAML (no `: ` inside `description`); `tests/test_skills.py` checks this.
- Update `skills/printerval-blog-seo/references/sources.md` whenever a new source is used, and state its verification level.
