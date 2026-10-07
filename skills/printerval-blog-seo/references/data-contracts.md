# Data contracts: schema of the CSV files in the pipeline

Every file is UTF-8 CSV with a header row (the final plan is also written as .xlsx). Column names are fixed so that the skills connect to one another; new columns are only ever added at the end.

## SEO specialist input (read directly by keyword-clustering)

CSV or Excel (`.xlsx`: **every** sheet with a keyword column within its first 40 rows; `source_file` is then `file.xlsx [Sheet]`). Only a keyword column is required. The other columns are detected by name automatically (case-insensitive, NFC-normalised, ignoring a trailing parenthesised part). Real headers per tool: `keyword-clustering/references/export-formats.md`.

| Standard column | Column names recognised |
|---|---|
| keyword | Keyword, Keywords, Query, Top queries, Search term, Phrase, Từ khóa |
| volume | Volume, Search Volume, Avg. monthly searches, Monthly searches, SV |
| impressions / clicks | Impressions, Clicks (GSC; used as volume only when there is no volume column, with a warning) |
| kd | Personal Keyword Difficulty (preferred), KD, KD %, Keyword Difficulty, Keyword Difficulty Index, Difficulty |
| cpc | CPC, CPC (USD) |
| market | Market, Country, Location, Geo, Database |
| serp | serp_urls, Top URLs, SERP (the top-10 URLs, separated by a pipe or whitespace) |
| intent | Intent, Intents, Keyword Intents (words, Semrush API codes 0–3, I/N/C/T letters) |
| parent | Parent Topic, Parent Keyword (Ahrefs) |
| position | Position, Avg. position, Current position |
| serp_features | SERP Features, SERP Features by Keyword |
| trend | Trend, Trends, SV trend (MM-YYYY - MM-YYYY) |
| traffic_potential | Traffic potential |
| ranking_url | URL, Current URL |
| flag_branded, flag_local, flag_informational, flag_commercial, flag_transactional, flag_navigational | Branded, Local, Informational, Commercial, Transactional, Navigational (Ahrefs Site Explorer true/false) |
| monthly searches | `Searches: Mon YYYY` (Keyword Planner; matched by pattern, not by `--map`) |
| competitive_density, results, click_potential, change_3m, change_yoy | Competitive Density, Number of Results, Click potential, Three month change, YoY change (recognised, not used yet) |
| group, main, secondary, role, pillar | Cluster, Group, Keyword Group, Nhóm, Cụm, Chủ đề / Main Keyword, Primary Keyword, Page, Từ khóa chính / Secondary Keyword(s), Từ khóa phụ / Page type, Category Kind / Pillar, Thuộc Pillar; `Topic` is the pillar when `Page` is present, else the group (recognised; an existing grouping is not used yet and the report warns) |
| stt, status, url_blog, category | STT / Trạng thái, Status / URL Blog, Target URL / Category, Danh mục (recognised, not used) |

Never used as a value: `Global volume`, `Global traffic potential`, `Competition` (ads), `SV Forecasting trend`, `#`; they are listed as ignored on purpose in `cluster-report.md`.

Unusual columns: `--map keyword="Top queries" volume=Impressions` (any standard column above).

**Market of a row:** its market cell; otherwise the `file::us` suffix, the market in the tool's file name (`_us_2026-05-01`, `-organic.Positions-uk-`, `google_gb_`), the Search Console `Country` filter, `--market`; otherwise `all`. `gb` = `uk`. Rows of any other market are excluded with the reason `market:<code>`.

## keyword-clustering output

**`clusters.csv`** (one row per cluster = one blog post): `cluster_id, market, cluster_name, keyword_count, seed_volume, cluster_volume, seed_kd, kd_min, reader_need, blog_fit, occasion, recipient, interest, product, style, craft, theme, core, category, season, market_terms, parent_topic, keywords, name_fluency, grouping_basis, serp_verified_share, seed_basis, prior_group, prior_pillar, prior_role, intents_mix, serp_features_main, traffic_potential_main, cluster_volume_dedup, peak_month, ramp_month, peak_ratio, seasonality_source, decision_ids`

**`keyword-map.csv`** (one row per keyword): `cluster_id, market, keyword, volume, volume_estimated, kd, cpc, is_seed, reader_need, blog_fit, occasion, recipient, interest, product, style, craft, theme, category, market_terms, parent_topic, intent_source, variants, source_file, spelling_fixed, variant_volumes, normalized_keyword, joined_by, need_source, prior_group, prior_main, prior_role, prior_pillar, intents, intent_branded, intent_local, serp_features, traffic_potential, ranking_url, position, trend, trend_end, peak_month, volume_range, volume_sources, kd_source, decision_ids`

- `theme` ∈ the theme keys of `assets/taxonomy.json` (dates, history, meaning, facts, printables, humor, crafts, decor, images, world, gifts, events, activities, food, messages) or empty. `core` = the words that say what the keyword asks once the topic, the theme's generic words and stop words are removed (space-separated; empty = the broad question of the theme).
- `variants` / `variant_volumes`: same-meaning variants merged into this keyword (word order, a year, a fixed typo) and their volumes, `|`-separated. `spelling_fixed` = 1 when a typo or split word was corrected before matching.
- `name_fluency`: how natural the cluster's name reads (mean log probability per word pair, learned from the file; higher = more natural, usually -1 to -4). topic-map uses it to break ties when naming a post.

Evidence columns of `keyword-map.csv` (empty when the export has no such data):

- `normalized_keyword`: the keyword's canonical tokens, sorted and space-separated (spelling fixed, UK→US, plurals and years removed).
- `joined_by`: how the keyword joined its cluster: `seed` (the cluster's first keyword), `serp:<n>` (n shared SERP URLs), `parent` (same Parent Topic, `--trust-parent-topic`), `lexical:<similarity>` (weighted Jaccard, 2 decimals), `core:<core words>` (absorbed when clusters asking the same question were consolidated; `core:-` = empty core).
- `need_source`: `rule` (the taxonomy regexes and themes) or `conflict: regex shop vs <tool> <intents>` / `conflict: regex shop vs SERP features <features>`: the regex gave `shop` only through the product fallback while the tool's intent was informational/commercial or the SERP had paa/featured_snippet/ai_overview, so the need was recomputed without that fallback (see `keyword-clustering/references/reader-needs.md`).
- `intents`: the tool's intent labels, `|`-separated, from {informational, commercial, transactional, navigational}. `intent_branded` / `intent_local`: 1, 0 or empty (Ahrefs). `intent_source` keeps the raw cell.
- `serp_features`: slugs, `|`-separated (`paa`, `featured_snippet`, `ai_overview`, `image_pack`, `video`, `shopping`, `local_pack`, `top_stories`, `knowledge_panel`, `discussions`, `ads`, `sitelinks`, `things_to_know`, `reviews`, `instant_answer`, `thumbnail`, or `other:<name>`).
- `traffic_potential`: Ahrefs Traffic potential. `ranking_url` / `position`: the URL that ranks and its position (positions exports, Ahrefs Site Explorer; GSC Position); when rows are joined, the best position and its URL.
- `trend`: comma-separated values, oldest first: relative 0–1 with 2 decimals (Semrush Trend, Organic Research Trends ÷100) or absolute monthly volumes (Ahrefs SV trend, Keyword Planner months). `trend_end`: `YYYY-MM` of the last value, only when the months are known (Keyword Planner with every month filled, Ahrefs SV trend whose length matches its header); `peak_month` (`Jan`...`Dec`, the latest on a tie) only then.
- `volume_range`: the range behind an estimated volume (`1K–10K`, from a text range or a Keyword Planner bucket value), else empty.
- `volume_sources`: every source of the keyword after exact duplicates were joined, `tool:value` `|`-separated, `~` before an estimate, `-` for an empty cell (`semrush-kmt:40500|ahrefs-ke:38000`, `gkp:~1000`). Tools: semrush-kmt, semrush-ksb, semrush-api, semrush-positions, ahrefs-ke, ahrefs-se, gkp, gsc, team-plan, generic. `kd_source`: the tool the KD came from.
- `prior_group, prior_main, prior_role, prior_pillar` (and `prior_*` in `clusters.csv`), `decision_ids`: reserved for back-checking an existing grouping and for review decisions; always empty in this version.

Columns of `clusters.csv` added for evidence:

- `grouping_basis` ∈ `single`, `serp`, `parent_topic`, `lexical (not verified by SERP)` (`lexical` and `core` joins), `mixed`.
- `serp_verified_share`: share of the cluster volume whose membership rests on shared SERP URLs or the Parent Topic (the seed counts once a member is verified), 2 decimals; empty for a single keyword.
- `seed_basis`: why the post is named after its main keyword: `max_volume`, `evergreen (no year)`, `spelled correctly`, `more natural phrasing`, `plain phrasing`.
- `intents_mix`: the members' tool intent labels with counts and volume (`informational (3 kw, 8,100) | no label (1 kw, 90)`); empty when no member has a label. `serp_features_main` / `traffic_potential_main`: those of the main keyword.
- `cluster_volume_dedup`: an estimate next to the `cluster_volume` sum; a keyword and its variants that report the **same** volume count once.
- `peak_month, ramp_month, peak_ratio, seasonality_source`: reserved for cluster seasonality from data; empty in this version.

**`merge-candidates.csv`**: `cluster_a, name_a, cluster_b, name_b, score, reason, evidence_type, volume_a, volume_b, need_a, need_b, theme_a, theme_b, core_a, core_b, guard_diff, keywords_a, keywords_b`. `evidence_type` ∈ lexical, serp, parent_topic; `guard_diff` lists the guard fields that differ (`interest: hunting vs -`); at most 300 pairs (the report says when the cap is hit).

**`spelling-fixes.csv`** (one row per learned correction): `kind, from, to, keywords_changed, examples, from_volume, to_volume, vetoed`. `kind` ∈ typo, join, split, completion; `from_volume` / `to_volume` = the volume of the keywords already typed with each form; `vetoed` is reserved (empty).

**`serp-check.csv`** (for the SEO to check on the live SERP, largest first, `--serp-check-max` rows, default 30): `market, keyword_a, volume_a, keyword_b, volume_b, why, current_grouping, question`. Rows are merge candidates near a threshold (`current_grouping` = `separate posts (C0003, C0010)`) and clusters grouped by words only (`same post (C0004)`).

Others: `excluded.csv` (keyword, volume, reason, source_file; reasons include `market:<code>`), `unclassified.csv`, `taxonomy-suggestions.csv`, `groups.csv/.md`, `cluster-report.md`.

Values: `reader_need` ∈ inspire, choose, how_to, solve, copy_ideas, info, shop. `blog_fit` ∈ high, medium, low (shop = low). `market` ∈ us, uk, all.

## topic-map.csv

`pillar_id, pillar_type, pillar_key, pillar_name, role, cluster_id, primary_keyword, planned_slug, post_type, reader_need, cluster_volume, priority_score, bucket, season, market, occasion, recipient, interest, product, craft, keywords, parent_hint, note, theme, merged_into`

- `role` ∈ pillar, cluster, standalone (the planned posts), merged (covered by the post `merged_into`, which may sit in another theme pillar of the same topic; no slug of its own), backlog (long tail that matches no theme pillar; not planned), skip (shopping intent). `post_type` ∈ pillar-hub, gift-guide, ideas-list, choose-guide, how-to, explainer, copy-ideas, merged, backlog, skip.
- A split topic has `pillar_key` = `<topic>/<theme>` (for example `thanksgiving/history`).
- `bucket` A/B/C by priority score (top 20% = A, up to 50% = B). `planned_slug` is a proposed slug (not a real URL).

## link-plan.csv

`source_slug, source_keyword, target_slug, link_type, anchor, anchor_alternatives, placement, priority, status, reason`

- `link_type` ∈ to_pillar, from_pillar, contextual, sibling, cross_pillar, orphan_fix, related, backlink_old_post. The final plan's Internal Link column takes every type except `sibling`; Related Post takes the siblings.
- `status` ∈ include_in_draft, include_in_draft_target_not_live_yet, existing_verify_present, update_old_post_after_target_live.

## seasonal-plan.csv

`planned_slug, post_type, role, season, market, event_date, publish_new_by, refresh_existing_by, days_to_publish_by, status, note`; `status` ∈ upcoming, due_soon, overdue, no_calendar_rule.

## final-plan.xlsx / final-plan.csv (export_plan.py)

Sheet **Plan**, one row per planned post: `STT, Main Keyword, Secondary Keyword, Volume, KD, Category, Category Kind, Thuộc Pillar, Title SEO, Meta Description SEO, Outline, Internal Link (Anchor || URL), Related Post (Anchor || URL), URL Blog, Trạng thái`

- Empty for the content team: Category, Title SEO, Meta Description SEO, Outline, Trạng thái.
- `Category Kind` ∈ Pillar, Cluster; `Thuộc Pillar` = the pillar's Main Keyword for a Cluster, empty for a Pillar (or for a standalone post without a pillar).
- `Secondary Keyword`, `Internal Link`, `Related Post`: one item per line (`anchor || URL` for links). In the .xlsx the link cells are formulas that read `URL Blog` of the target row by STT; the .csv has plain text (UTF-8 with BOM).

Sheet **Keyword Map**: `STT, Main Keyword, Keyword, Volume, KD, Role` with Role ∈ main, secondary, also covers, variant.

Sheet **Schedule**: `Order, STT, Main Keyword, Category Kind, Priority, Volume, KD, Season, Event Date, Publish By, Status, Note`; Status ∈ late: publish ASAP, due soon, on time, no date rule, evergreen.

Sheet **Research Next** (one-topic exports only): `Topic, Theme, Why It Matters, Keywords In File, Volume In File, Status, Seeds To Export`; Status ∈ covered, thin, missing, suggested (occasion ideas).

Sheet **Published Match** (with `--published`): `STT, Main Keyword, Match, Published Title, URL, Category, Score, Advice`; Match ∈ update this post, also published, covers part of it, related live post, duplicate published posts, IP check. The published-posts input is any CSV/.xlsx whose header (within the first 20 rows of a sheet) has a URL column (`URL`, `Link`, `Permalink`...) and a title column (`Title`, `Tiêu đề`...); optional `Category` and a focus keyword column.

Sheet **Changes** (with `--previous`): `STT, Main Keyword, Change, Detail`; Change ∈ kept, renamed, new, dropped, kept from the previous plan.

Sheet **QA**: `Severity, Check, STT, Main Keyword, Detail, Suggestion`; Severity ∈ high, medium, low, info; Check ∈ overlap, misplaced, year_in_main, slug, overloaded, thin_links, weak_post, hard_keyword (`scripts/plan_qa.py`; heuristics for a person to review).

## Markers in a post

| Marker | Meaning |
|---|---|
| `[PRODUCT-SLOT: ...]` (full syntax in the `product-slot` skill) | a place to mention a product; the content team replaces it with a link |
| `[EXPERIENCE: source]` | real first-hand experience, with an internal source that can be verified |
| `[DATA: source]` / `[DATA NEEDED: ...]` | a figure with a source / a figure that is still missing |
| `[LINK: topic]` | an internal link whose target post does not exist yet |
| `[CLAIM-OK: reason; approver; date]` | a claim approved by someone with authority (claims_check skips it) |
