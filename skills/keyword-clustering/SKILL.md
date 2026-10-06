---
name: keyword-clustering
description: Reads keyword export CSV files from SEO specialists (Semrush, Ahrefs, Google Keyword Planner, Search Console, Google Sheets; from small files to hundreds of thousands of rows) and clusters the keywords on request by occasion, recipient, interest, product, reader intent, custom categories or SERP overlap. Filters noise transparently, separates US and UK, and writes a verification report. Use when the user sends or mentions a keyword file, or asks to cluster, group, filter or map keywords for the Printerval blog.
---

# Keyword clustering: read real exports, group on request

Turns a very broad keyword file into **clusters** (each cluster = one blog post) and then **groups** (the clusters along the dimension you need). Reply in the user's language; keywords and deliverables stay in English.

## Workflow

1. **Receive the file and the request.** Establish: market (US/UK), the dimension to group by, filters (volume, KD, words to drop or keep) and the desired granularity. If something is missing, use the defaults and state the assumption (see the table below). Ask only when the request is genuinely ambiguous.
2. **First run with default settings plus the request:**
   ```bash
   python3 skills/keyword-clustering/scripts/cluster_keywords.py export.csv --out outputs --group-by occasion,recipient
   ```
   Several files or markets: `us.csv::us uk.csv::uk` (a file with a Country column is recognised automatically).
3. **Read `outputs/cluster-report.md` first.** Check, in this order:
   - *Input*: are the encoding, delimiter and header row plausible; which columns were recognised; the volume source (real `volume`, or only GSC `impressions`).
   - *Filters*: which keywords were excluded and why. Open `excluded.csv`, sort by volume and look for false exclusions (for example "boots" is no longer treated as a retailer; "mama bear shirt" is not Spanish). If something is wrong, edit `assets/noise-rules.json` or turn the filter off with `--no-noise-filter`.
   - *Result*: the share of single-keyword clusters (>70% means the threshold is too strict or the data is very diverse: try `--granularity loose`).
   - *Unclassified*: if more than 15% of the volume, read `taxonomy-suggestions.csv` (frequent n-grams in unrecognised keywords), propose taxonomy additions (see `references/taxonomy-guide.md`), then re-run with `--extend-taxonomy`.
4. **Review `merge-candidates.csv`** (cluster pairs near the merge threshold): read each pair, decide "merge / keep apart / leave", and record the decision for the user. When real SERP data (`serp_urls`) exists, trust it over vocabulary.
5. **Hand over** `clusters.csv` + `cluster-report.md` (+ `groups.md` when `--group-by` was used) with: the assumptions used, the real figures (read / excluded / clusters), and the points that need a person's decision. Next step: `topic-map`.

## Translating an SEO specialist's request into options

| They say | Option |
|---|---|
| "Only the US/UK market" / the file is for the UK | `file.csv::uk` or `--market uk` |
| "Group by recipient / occasion / interest / product" | `--group-by recipient` (or occasion, interest, product, style, craft) |
| "Group by occasion, then by recipient" | `--group-by occasion,recipient` (nested) |
| "Group by reader intent (ideas, how-to, comparison...)" | `--group-by intent` |
| "Group by my own groups: Family, Work, Pets..." | `--categories categories.json --group-by category` (see `examples/categories-example.json`) |
| "Only Mother's Day and Father's Day" | `--only occasion=mothers-day,fathers-day` |
| "Only keywords about dogs/cats" | `--only interest=dogs,cats` or `--include "\bdogs?\b" --include "\bcats?\b"` (several `--include` = or) |
| "Drop brand/competitor/free/pdf keywords" | `--exclude "\bfree\b" --exclude "\bpdf\b"` (retailers and brands are already excluded by default) |
| "Drop low-volume / very high-volume keywords / KD > 60" | `--min-volume 100`, `--max-volume 50000`, `--max-kd 60` |
| "Drop shopping keywords" | `--drop-shop` (by default they are only tagged `blog_fit=low`, not removed) |
| "Smaller / more detailed clusters" or "broader clusters" | `--granularity tight` / `--granularity loose` (or `--sim 0.7`) |
| "The file has a top-10 SERP column" | a `serp_urls` column; the script clusters by SERP overlap automatically (`--serp-overlap 4`) |
| "The Ahrefs file has Parent Topic" | `--trust-parent-topic` to merge by that column |
| "A column has a different name" | `--map keyword="Top queries" volume=Impressions` |
| "I want to save the settings and re-run" | `--request request.json` (see `examples/request-example.json`) |

**Complex requests** ("Mother's Day by recipient, Father's Day by interest"): run several times, each with its own `--only` and `--group-by`, write to different `--out` folders, then combine the results for the user. Unclear requests ("group it sensibly"): use the defaults and say what you chose and why.

Valid facets and values for `--only` and `--group-by`: `assets/taxonomy.json`. `intent` means `reader_need`: inspire, choose, how_to, solve, copy_ideas, info, shop.

## Supported file formats

Handled automatically: UTF-8, UTF-8 with BOM, **UTF-16 + tab** (Keyword Planner, some Ahrefs exports), cp1252; description lines above the header (Keyword Planner); delimiters `, ; tab |`; numbers such as `1,234`, `1.234`, `1K`, `1.2M`, `1K - 10K` (a range: the lower bound is read and flagged as an estimate; change with `--range-mode mid`), `<10`, `35%`. Column details and pitfalls per tool: `references/export-formats.md`. For `.xlsx` files, export to CSV first (or use the `xlsx` skill).

## How the script clusters (to explain and verify)

- **Normalisation:** lowercase, apostrophes removed (`mother's` -> `mothers`), hyphens -> spaces, UK->US variants for matching (mum->mom, personalised->personalized, nan->grandma), years dropped (`2026`), simple plurals removed. Same-meaning variants within one market are merged first, keeping the highest-volume keyword.
- **Facet detection** with regexes in the taxonomy: occasion, interest, recipient, product, style, craft; every keyword gets a `reader_need` and a `blog_fit` (shop = `low`: pure shopping intent, left to the shop pages and content team).
- **Seed-based clustering** (the highest-volume keyword is the seed): at least N shared SERP URLs, or weighted Jaccard >= the threshold (words such as "gift", "ideas" and "best" weigh 0.3). Two keywords are merged lexically only when they share the **market, the intent group (inspire~choose count as one) and the same occasion / recipient (including implied: mother's day -> mom) / interest / product**.
- **Performance:** inverted index + prefix filter (exact: no pair that meets the threshold is missed; each posting list is capped at about 3,000 entries), so 150,000 keywords take about a minute.

**Limits to state plainly:** vocabulary does not understand deep synonyms (two very different phrasings of one idea can land in two clusters); `cluster_volume` is a sum, so it is an upper bound; facet regexes can miss new niches (see `taxonomy-suggestions.csv`); SERP overlap is more accurate but needs real SERP data for each market.

## Do not

- Do not invent volume or KD when the file has none; warn and explain the consequence.
- Do not merge US with UK (different SERPs, different vocabulary).
- Do not drop keywords silently: every excluded keyword must be in `excluded.csv` with a reason.
- Do not turn each keyword variant into a post (scaled content abuse); one cluster = one post.

## Related documents

- `references/export-formats.md`: columns and quirks of Semrush/Ahrefs/Keyword Planner/GSC files.
- `references/reader-needs.md`: the seven reader needs, the detection rules, `blog_fit`.
- `references/taxonomy-guide.md`: extending the taxonomy (new niches, occasions), creating `categories.json`, noise rules.
- `assets/taxonomy.json`, `assets/noise-rules.json`: editable configuration.
