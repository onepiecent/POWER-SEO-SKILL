# Data contracts: schema of the CSV files in the pipeline

Every file is UTF-8 CSV with a header row (the final plan is also written as .xlsx). Column names are fixed so that the skills connect to one another; new columns are only ever added at the end.

## SEO specialist input (read directly by keyword-clustering)

CSV or Excel (`.xlsx`, the first sheet with a keyword column). Only a keyword column is required. The other columns are detected by name automatically (case-insensitive, ignoring a trailing parenthesised part):

| Standard column | Column names recognised |
|---|---|
| keyword | Keyword, Keywords, Query, Top queries, Search term |
| volume | Volume, Search Volume, Avg. monthly searches, Monthly searches |
| impressions / clicks | Impressions, Clicks (GSC; used as volume only when there is no volume column, with a warning) |
| kd | KD, KD %, Keyword Difficulty, Difficulty |
| cpc | CPC, CPC (USD) |
| market | Market, Country, Location, Geo |
| serp | serp_urls, Top URLs, SERP (the top-10 URLs, separated by a pipe or whitespace) |
| intent | Intent, Intents (kept for reference only) |
| parent | Parent Topic, Parent Keyword (Ahrefs) |
| position | Position, Avg. position (GSC) |

Unusual columns: `--map keyword="Top queries" volume=Impressions`.

## keyword-clustering output

**`clusters.csv`** (one row per cluster = one blog post): `cluster_id, market, cluster_name, keyword_count, seed_volume, cluster_volume, seed_kd, kd_min, reader_need, blog_fit, occasion, recipient, interest, product, style, craft, theme, core, category, season, market_terms, parent_topic, keywords, name_fluency`

**`keyword-map.csv`** (one row per keyword): `cluster_id, market, keyword, volume, volume_estimated, kd, cpc, is_seed, reader_need, blog_fit, occasion, recipient, interest, product, style, craft, theme, category, market_terms, parent_topic, intent_source, variants, source_file, spelling_fixed, variant_volumes`

- `theme` ∈ the theme keys of `assets/taxonomy.json` (dates, history, meaning, facts, printables, humor, crafts, decor, images, world, gifts, events, activities, food, messages) or empty. `core` = the words that say what the keyword asks once the topic, the theme's generic words and stop words are removed (space-separated; empty = the broad question of the theme).
- `variants` / `variant_volumes`: same-meaning variants merged into this keyword (word order, a year, a fixed typo) and their volumes, `|`-separated. `spelling_fixed` = 1 when a typo or split word was corrected before matching.
- `name_fluency`: how natural the cluster's name reads (mean log probability per word pair, learned from the file; higher = more natural, usually -1 to -4). topic-map uses it to break ties when naming a post.

Others: `excluded.csv` (keyword, volume, reason, source_file), `unclassified.csv`, `taxonomy-suggestions.csv`, `merge-candidates.csv`, `groups.csv/.md`, `cluster-report.md`.

Values: `reader_need` ∈ inspire, choose, how_to, solve, copy_ideas, info, shop. `blog_fit` ∈ high, medium, low (shop = low). `market` ∈ us, uk, all (or another original value).

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

Sheet **QA**: `Severity, Check, STT, Main Keyword, Detail, Suggestion`; Severity ∈ high, medium, low, info; Check ∈ overlap, misplaced, year_in_main, slug, overloaded, thin_links, weak_post, hard_keyword (`scripts/plan_qa.py`; heuristics for a person to review).

## Markers in a post

| Marker | Meaning |
|---|---|
| `[PRODUCT-SLOT: ...]` (full syntax in the `product-slot` skill) | a place to mention a product; the content team replaces it with a link |
| `[EXPERIENCE: source]` | real first-hand experience, with an internal source that can be verified |
| `[DATA: source]` / `[DATA NEEDED: ...]` | a figure with a source / a figure that is still missing |
| `[LINK: topic]` | an internal link whose target post does not exist yet |
| `[CLAIM-OK: reason; approver; date]` | a claim approved by someone with authority (claims_check skips it) |
