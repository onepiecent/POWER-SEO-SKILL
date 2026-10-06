# Characteristics of each tool's export file

`kw_ingest.py` detects the file type (CSV or Excel `.xlsx`), encoding, delimiter, header row and column names automatically. The table below lists typical cases; actual column names can differ by tool version, so always check the "Recognised columns" table in `cluster-report.md`.

| Source | Columns usually present | Things to watch |
|---|---|---|
| **Semrush** (Keyword Magic Tool, Organic Research) | Keyword, Intent, Relevance, Volume (or Search Volume), Keyword Difficulty, CPC (USD), Competitive Density, Number of Results, Trend, SERP Features | Exported as **`.xlsx`** by default (read directly; the first sheet with a Keyword column). `Intent` is Semrush's own label (it can hold several values): it is kept only in `intent_source` and is not used for clustering; `Relevance` is ignored. Data is per the selected country "database" and usually has no country column: assign one with `file.xlsx::us` or `--market us`. **"All keywords" is broad match**: a "thanksgiving day" export also holds Labor Day, Mother's Day... (in a real file only ~11,000 of 30,000 rows were about Thanksgiving); keep the topic with `--only occasion=thanksgiving`. |
| **Ahrefs** (Keywords Explorer, Organic keywords) | Keyword, Country, Difficulty (KD), Volume, CPC, Parent Topic / Parent Keyword, SERP Features, Traffic potential | The export can be UTF-16 or UTF-8 depending on the option; the script detects it. `Parent Topic` is computed by Ahrefs from the SERP: use `--trust-parent-topic` to merge by this column, or let the script suggest merges in `merge-candidates.csv`. The Country column allows an automatic US/UK split. |
| **Google Keyword Planner** | Keyword, Currency, Avg. monthly searches, Three month change, YoY change, Competition, Top of page bid... | Usually **UTF-16, tab-delimited** with a `.csv` extension, and 1-3 description lines above the header (handled). Accounts that do not run ads often get volume as a **range** ("1K - 10K"): the lower bound is read and `volume_estimated=1` is set (change this with `--range-mode mid` or `--range-mode high`). The `Competition` column is advertising competition, not SEO KD, so it is not used as KD. |
| **Google Search Console** (Performance, Queries) | Top queries, Clicks, Impressions, CTR, Position | There is no market volume. The script uses **Impressions** as volume and **warns**: this is demand the site has already been shown for, not the whole opportunity. Use GSC to find gaps or improve old posts; combine it with a volume file from a keyword tool. |
| **Google Sheets / hand-made** | varies | Only a keyword column is needed. If a column has an unusual name: `--map keyword=<column name> volume=<column name>`. |
| **SERP API export (DataForSEO, SerpAPI...)** | keyword + the list of top-10 URLs | Put the URLs in a `serp_urls` column (separated by a pipe or whitespace). This is the **most accurate** way to cluster (at least 4 shared URLs = the same post). Each market needs the SERP of that market (google.com for US, google.co.uk for UK). |

## Tips for very large files

- Measured on 150,000 synthetic keywords: about 70 seconds, peak RAM about 580 MB (Python 3.13). A linear estimate: 500,000 rows need about 2 GB of RAM. A real 30,000-row Semrush export takes about 10 seconds. For files with millions of rows, split by market or by seed first (for example one file per seed), or filter with `--min-volume` from the start. Real data can be slower than synthetic data.
- Most keywords in a broad export are noise for a blog (retailers, "near me", Spanish...). The default filters drop them **with a reason** in `excluded.csv`; do not turn them off without a reason.
- Several files on the same topic: pass several paths at once; duplicate keywords are merged (the largest volume is kept, volumes are not summed across files).

## When the script says "No header row ... found"

Open the first 5 lines that it prints. If the keyword column has an unusual name, run again with `--map keyword="<exact column name>"`. If the file has no header row, add a `keyword,volume` line at the top.
