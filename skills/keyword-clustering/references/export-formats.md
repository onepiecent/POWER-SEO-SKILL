# Characteristics of each tool's export file

`kw_ingest.py` detects the file type (CSV or Excel `.xlsx`), encoding, delimiter, header row and column names automatically, and `kw_evidence.py` names the tool that wrote the file and reads its evidence columns (intent, SERP features, trend, monthly searches). The headers below are copied from **real export files** published on GitHub and run through the ingest (level **D** in `printerval-blog-seo/references/sources.md`); what a column *means* comes from vendor documentation read through search summaries (level **S**, [Convention: vendor docs]). Tools change their headers and users can choose columns, so always check three sections of `cluster-report.md` §1: *Source tool, market and sheets*, *Columns used as evidence* and *Ignored columns*.

## What every file gets

- **Every sheet** of an `.xlsx` that has a keyword column (within its first 40 rows) is read, for example one sheet per group in a Semrush "export with groups" or a hand-made workbook. `source_file` becomes `file.xlsx [Sheet name]`; skipped sheets are listed with the reason (`empty`, `no keyword column in the first 40 rows`).
- **A quoted cell that spans several lines** (Alt+Enter in Sheets or Excel, KSB `Content references`) stays one cell; it is not glued to the next line.
- **Headers are NFC-normalised** before matching, so Vietnamese headers typed with composed or decomposed accents (`Từ khóa`, `Từ khoá`) are the same column.
- **Ignored columns** are listed per file. Some are ignored on purpose and say why: `Global volume` and `Global traffic potential` (worldwide, never the US/UK volume), `Competition` (advertising competition, not SEO difficulty), `SV Forecasting trend` (a forecast, not measured searches), `#` (row number).
- **Markets other than US and UK** (`au`, `ca`, `pk`...) are excluded with the reason `market:<code>` in `excluded.csv`; they are not planned as silent extra markets. Ahrefs' `gb` is read as `uk`.
- **Grouping columns** (Cluster, Group, Main Keyword, Secondary Keyword, Page, Topic, Pillar, Page type, Thuộc Pillar, Category Kind, Nhóm, Cụm, Chủ đề) are recognised, but reading an existing grouping and back-checking it is not built yet: the report warns, and the keywords are clustered as a raw export.

## Semrush

### Keyword Magic Tool (KMT): `semrush-kmt`

| | |
|---|---|
| Real header, 2026 (D) | `Keyword,Intent,Volume,Trend,Keyword Difficulty,CPC (USD),Competitive Density,SERP Features,Number of Results`. Columns can be switched off, so 6-column files (`Keyword,Intent,Volume,Keyword Difficulty,CPC (USD),SERP Features`) also occur. 2019–2020 files have no Intent, give KD as a decimal (`85.18`) and use another order. A UK-database file still says `CPC (USD)`. |
| File name (D) | `<seed>_broad-match_us_2026-05-01.csv`, `<seed>_all-keywords_us_2026-05-04.csv`: the `_<db>_YYYY-MM-DD` token gives the market and the export date. |
| Read as | keyword, volume, kd, cpc, `Intent` → `intents`, `SERP Features` → `serp_features`, `Trend` → `trend` (relative). `Competitive Density` and `Number of Results` are recognised and not used. |
| Watch out | The default export is **`.xlsx`** (read directly). **"All keywords" is broad match**: a "thanksgiving day" export also holds Labor Day, Mother's Day... (in a real file only about 11,000 of 30,000 rows were about Thanksgiving); keep the topic with `--only occasion=thanksgiving`. Long-tail rows often have Intent and KD empty and Volume 0: an empty KD is unknown, never 0. There is no `Relevance` column in any real export found. |

`Volume` is the average of the last 12 months [Convention: vendor docs]. `Trend` holds up to 12 values from 0 to 1, scaled so the peak month is 1.00, **oldest to newest** (checked on real Christmas and Halloween rows, D). The file does not say which calendar months the values are, so `keyword-map.csv` keeps the series but leaves `trend_end` and `peak_month` empty: month names are never guessed.

### Keyword Strategy Builder / Keyword Manager (KSB): `semrush-ksb`

| | |
|---|---|
| Real header (D) | `Database,Keyword,Seed keyword,Page,Topic,Page type,Tags,Volume,Keyword Difficulty,CPC (USD),Competitive Density,Number of Results,Intent,SERP Features,Trend,Click potential,Content references,Competitors` |
| File name (D) | `<name>_clusters_YYYY-MM-DD.csv`, `<name>_list_YYYY-MM-DD.csv`: the export date only, no market. |
| Read as | `Database` → market per row (one real file mixed `us` and `au`; the `au` rows are excluded), Intent, SERP Features (Title Case: `Site Links, People Also Ask, Adwords Bottom`), Trend. `Page` (the post's main keyword), `Topic` (the pillar when `Page` is present) and `Page type` (`Pillar page`, `Sub page`) are recognised as grouping columns, which are not used yet (warning). `Click potential` is recognised and not used. |
| Watch out | `Content references` and `Competitors` hold 10 multi-line `"domain":"url"` pairs that are **the same for every keyword of a Page**: they are the page's reference SERP, not a SERP per keyword. They are never read as `serp_urls` (that would merge every keyword of the page by construction) and appear under *Ignored columns*. In a `_list_` export most rows have no Page. |

### Semrush API and semicolon exports: `semrush-api`

| | |
|---|---|
| Real headers (D) | `database;Keyword;Search Volume;Keyword Difficulty Index;Intent` (rows like `us;applicant tracking system;8100;68;1,0`) and `Keyword;Search Volume;CPC;Competition;Number of Results;Keyword Difficulty Index` |
| Read as | `database` → market, `Keyword Difficulty Index` → kd, `Intent` codes → `intents`. The `;` delimiter is detected. |
| Watch out | `Intent` holds number codes: 0 = Commercial, 1 = Informational, 2 = Navigational, 3 = Transactional [Convention: Semrush API docs, S]; `1,0` becomes `commercial|informational`. `Competition` here is ad competition from 0 to 1 and is ignored on purpose. SERP features given as number codes are **not decoded** (the mapping was not verified): they are kept as `other:<code>`. |

### Organic Research positions: `semrush-positions`

| | |
|---|---|
| Real headers (D) | `Keyword,Position,Previous position,Search Volume,Keyword Difficulty,CPC,URL,Traffic,Traffic (%),Traffic Cost,Competition,Number of Results,Trends,Timestamp,SERP Features by Keyword,Keyword Intents,Position Type`; a 2026 variant is `Keyword,Position,Search Volume,Traffic,URL,Keyword Difficulty,CPC,Keyword Intents,SERP Features by Keyword`. |
| File name (D) | `<domain>-organic.Positions-<db>-<YYYYMMDD>-<timestamp>Z.csv`: market and date. |
| Read as | `Position` → `position`, `URL` → `ranking_url` (the page of that domain that ranks), `Keyword Intents` (lowercase words) → `intents`, `SERP Features by Keyword` → `serp_features`, `Trends` → `trend`. |
| Watch out | The same keyword is listed **once per ranking URL**: the rows are joined into one keyword (the best position and its URL are kept), never summed. `Trends` uses integers from 0 to 100 in brackets (`[100,82,…]`), read as relative values divided by 100. A 2026 file writes SERP features as snake_case codes (`people_also_ask,ai_overview,local_pack,knowledge_graph,organic,paid`); `organic` is not a feature and is skipped. |

## Ahrefs

### Keywords Explorer: `ahrefs-ke`

| | |
|---|---|
| Real header, 2025 (D) | `#,Keyword,Country,Difficulty,Volume,CPC,CPS,Parent Keyword,Last Update,SERP Features,Global volume,Traffic potential,Global traffic potential,First seen,Intents`. A 2026 file adds `Languages,SV trend (09-2024 - 08-2026),SV Forecasting trend (09-2026 - 09-2027),Category`. 2020 files: `#,Keyword,Country,Difficulty,Volume,CPC,Clicks,CPS,Return Rate,Parent Keyword,Last Update,SERP Features,Global volume`. |
| File name (D) | `google_<db>_<seed>_matching-terms_YYYY-MM-DD_hh-mm-ss.csv`: market (`gb` → `uk`) and date. |
| Read as | `Country` (lowercase ISO: `us`, `gb`) → market, `Difficulty` → kd, `Parent Keyword` / `Parent Topic` → `parent_topic`, `Traffic potential` → `traffic_potential`, `SERP Features` (comma, no space: `People also ask,Top stories,Thumbnail`) → `serp_features`, `Intents` (`Informational,Commercial,Non-branded,Non-local`) → `intents` plus `intent_branded` / `intent_local`, `SV trend` → `trend` (absolute monthly volumes). |
| Watch out | `Global volume` is **never** the volume. `SV trend` holds monthly volumes (24 in the 2026 file) and the header names the months: when the number of values matches that range, `trend_end` and `peak_month` are filled. The export can be UTF-16 or UTF-8 (detected). `Parent Keyword` is computed by Ahrefs from the #1 page [Convention: vendor docs]; with `--trust-parent-topic` the clusterer merges by it (`joined_by=parent`, counted as SERP evidence); without it, clusters that share a Parent Keyword are listed in `merge-candidates.csv` (`evidence_type=parent_topic`). The 2026 `Category` column is Ahrefs' topic category; it is recognised as `category` and not used. |

### Site Explorer, Organic keywords: `ahrefs-se`

| | |
|---|---|
| Columns (D, from a real parser of this export) | Keyword, Volume, KD, CPC, Previous/Current organic traffic, Organic traffic change, Previous/Current position, Position change, Previous/Current position kind, Current URL, Previous URL, and **true/false** columns Branded, Local, Informational, Commercial, Transactional, Navigational. |
| Read as | `Current position` → `position`, `Current URL` → `ranking_url`, the true/false columns → `intents`, `intent_branded`, `intent_local`. |

## Google Keyword Planner: `gkp`

| | |
|---|---|
| Real layout, 2026 (D) | UTF-16, tab-delimited, `.csv` extension. Line 1 `Keyword Stats 2026-06-09 at 21_25_18`, line 2 `"May 1, 2025 - April 30, 2026"`, then the header: `Keyword, Currency, Avg. monthly searches, Three month change, YoY change, Competition, Competition (indexed value), Top of page bid (low range), Top of page bid (high range), Ad impression share, Organic impression share, Organic average position, In account?, In plan?, Searches: May 2025 … Searches: Apr 2026`. Some exports add `Segmentation`. |
| Read as | keyword, `Avg. monthly searches` → volume, the `Searches: Mon YYYY` columns → a monthly series with real calendar months (`trend`, absolute; `trend_end` and `peak_month` only when every month is filled). `Three month change` and `YoY change` are recognised and not used yet. |
| Watch out | **Bucket values.** Accounts with low ad spend get ranges [Google, S]. Real exports write them as `0, 50, 500, 5000, 50000, 500000` with every monthly column empty. When every non-empty volume of a file is such a value and every `Searches:` cell is empty, the file is read as buckets [Research: observed in real exports, D]: 0 → 0–10, 50 → 10–100, 500 → 100–1K, 5000 → 1K–10K, 50000 → 10K–100K, 500000 → 100K–1M, 5000000 → 1M–10M. Each row gets `volume_estimated=1`, `volume_range` and the bound that `--range-mode` picks (`low` by default), exactly like a range typed as text (`"1K – 10K"`). A file whose monthly columns are filled stays exact. `Competition` is advertising competition and is ignored on purpose. There is no market column: add `::us` / `::uk` or `--market`. A French-UI export kept English headers but wrote Competition in French and bids with decimal commas. |

## Google Search Console: `gsc`

| | |
|---|---|
| Real files (D) | `Queries.csv`: `Top queries,Clicks,Impressions,CTR,Position` (CTR like `45.61%`). `Filters.csv`: `Filter,Value` with rows such as `Search type,Web`, `Date,Last 3 months`, and `Country,United States` when a country filter is on. The `.xlsx` export has the sheets Queries, Pages, Countries, Devices, Search appearance, Dates and Filters; only Queries has a keyword column. |
| Read as | There is no market volume: **Impressions** is used as volume with a warning (demand the site was already shown for, not the whole opportunity). The market comes from the `Country` filter, read from the Filters sheet or a `Filters.csv` beside the queries file. |
| Watch out | UI exports stop at **1,000 rows** [Google]: a file of exactly 1,000 rows is flagged as probably cut off (use the API or the bulk export). No country filter → warning: impressions mix every country. Anonymized queries are never in the export [Google]. Use GSC to find gaps or refresh old posts, combined with a volume file from a keyword tool. |

## Hand-made sheets and SERP API exports

- **Google Sheets / hand-made:** only a keyword column is needed (`Keyword`, `Query`, `Từ khóa`...). If a column has an unusual name: `--map keyword="<column name>" volume="<column name>"` (every canonical name in `printerval-blog-seo/references/data-contracts.md` can be mapped).
- **SERP API export (DataForSEO, SerpAPI...):** keyword + the top-10 URLs in a `serp_urls` column (pipe or whitespace separated). This is the **most accurate** way to cluster (at least 4 shared URLs = the same post) [Convention: vendor thresholds differ]. Each market needs the SERP of that market (google.com for US, google.co.uk for UK).

## The same keyword more than once

- **Exact duplicates are one keyword.** The same text in the same market (ignoring only case, spacing and curly quotes), from several files or repeated in one file, is joined into one keyword **before** anything is summed. Its volume is chosen as follows: an exact value beats an estimate (a range or bucket), which beats GSC impressions or clicks, which beats an empty cell; then the larger value wins. KD and trend come from the same source when it has them. Intents, SERP features and SERP URLs are united; other fields keep the first value in file order. `volume_sources` in `keyword-map.csv` lists every source (`semrush-kmt:40500|ahrefs-ke:38000`; `~` marks an estimate, `-` an empty cell), and `kd_source` names the tool the KD came from. The report counts the joined rows (§2).
- **Variants are different searches.** Different texts with one meaning (word order, a year, a fixed typo, `when's` / `when is`) are merged as variants of one keyword and their volumes are **added** to `cluster_volume` (an upper bound, because many searchers overlap). `cluster_volume_dedup` (an estimate) counts a keyword and its variants that report the same volume once, since tools often give one figure for close variants [Google, S: Keyword Planner includes close variants]. Both numbers are shown.

## Value mappings [Convention: vendor docs]

**Intent** (`intents` in `keyword-map.csv`, `|`-separated): Semrush words in any case (`Commercial, Informational`), Semrush API codes (`0`–`3`, see above), the `I / N / C / T` badges copied from the Semrush UI, Ahrefs `Intents` words, and Ahrefs Site Explorer true/false columns all become `informational`, `commercial`, `transactional`, `navigational`. `Branded`/`Non-branded` and `Local`/`Non-local` become `intent_branded` / `intent_local` (1, 0 or empty). A label is the tool's hint, assigned by a model from the SERP and the words [Convention: vendor docs]; it is evidence next to the regex reader need, not proof (see `reader-needs.md`, *need_source*).

**SERP features** (`serp_features`, `|`-separated slugs; case, `_` and spacing ignored):

| Slug | Names seen in exports |
|---|---|
| `featured_snippet` | Featured snippet |
| `paa` | People also ask |
| `ai_overview` | AI Overview |
| `image_pack` | Image pack, Images, Featured images |
| `video` | Video, Videos, Video carousel, Video preview, Short videos, Featured video |
| `shopping` | Popular products, Shopping ads, Shopping results |
| `local_pack` | Local pack, Local results |
| `top_stories` | Top stories |
| `knowledge_panel` | Knowledge panel, Knowledge graph, Knowledge card |
| `discussions` | Discussions and forums |
| `ads` | Ads top, Ads bottom, Adwords top, Adwords bottom, Paid |
| `sitelinks` | Sitelinks, Site links |
| `things_to_know`, `reviews`, `instant_answer`, `thumbnail` | Things to know, Reviews, Instant answer, Thumbnail |
| `other:<name>` | anything else, including number codes (kept, not decoded) |

`paa`, `featured_snippet` and `ai_overview` count as an informational SERP for the need-vs-intent check [Convention]. The features themselves are Google's [Google]; FAQ and HowTo rich results no longer appear, so never promise them.

**Trend** (`trend` in `keyword-map.csv`):

| Format | Tool | Scale | Months known? |
|---|---|---|---|
| `0.20,1.00,0.82,…` (up to 12 values, peak = 1.00, oldest to newest) | Semrush KMT, KSB | relative | no: `trend_end` and `peak_month` stay empty |
| `[100,82,…]` (0–100) | Semrush Organic Research `Trends` | relative (÷100) | no |
| `2181, 1845, …` under `SV trend (MM-YYYY - MM-YYYY)` | Ahrefs Keywords Explorer | absolute | yes, when the count matches the header's range |
| `Searches: Mon YYYY` columns | Keyword Planner | absolute | yes, when every month is filled |

## Market of a file

Rows with a market cell (`Country`, `Database`, `Market`...) use it. Rows without one take, in this order: the `file.csv::us` suffix; the market in the tool's file name; the Search Console `Country` filter; `--market`; otherwise `all`. The report names the source for each file, and warns when the file name and `--market` disagree (the file name wins; add `::<market>` to override it).

| File-name pattern | Example | Market, date |
|---|---|---|
| `-organic.Positions-<db>-YYYYMMDD` | `site.com-organic.Positions-uk-20260628.csv` | uk, 2026-06-28 |
| `google_<db>_` | `google_gb_gifts_matching-terms_2026-07-08_20-05-24.csv` | uk, 2026-07-08 |
| `_(clusters\|list)_YYYY-MM-DD` | `gifts_clusters_2026-02-13.csv` | none, 2026-02-13 |
| `_<db>_YYYY-MM-DD` | `gifts_broad-match_us_2026-05-01.csv` | us, 2026-05-01 |

## Tips for very large files

- Measured on synthetic keywords (`tests/make_big_fixture.py`, Python 3.13): 50,000 rows take about 25 seconds with a peak of about 235 MB of RAM; 150,000 rows about 85 seconds and 660 MB (the evidence columns cost about 13% more memory than before). A linear estimate: 500,000 rows need about 2.2 GB of RAM. A real 30,000-row Semrush export takes about 10 seconds. For files with millions of rows, split by market or by seed first (for example one file per seed), or filter with `--min-volume` from the start. Real data can be slower than synthetic data.
- Most keywords in a broad export are noise for a blog (retailers, "near me", Spanish...). The default filters drop them **with a reason** in `excluded.csv`; do not turn them off without a reason.
- Several files on the same topic: pass several paths at once; exact duplicates are joined as described above.

## When the script says "No header row ... found"

Open the first 5 lines that it prints. If the keyword column has an unusual name, run again with `--map keyword="<exact column name>"`. If the file has no header row, add a `keyword,volume` line at the top.
