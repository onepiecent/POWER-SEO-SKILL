# Data contracts: schema of the CSV files in the pipeline

Every file is UTF-8 CSV with a header row. Column names are fixed so that the skills connect to one another.

## SEO specialist input (read directly by keyword-clustering)

Only a keyword column is required. The other columns are detected by name automatically (case-insensitive, ignoring a trailing parenthesised part):

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

**`clusters.csv`** (one row per cluster = one blog post): `cluster_id, market, cluster_name, keyword_count, seed_volume, cluster_volume, seed_kd, kd_min, reader_need, blog_fit, occasion, recipient, interest, product, style, craft, category, season, market_terms, parent_topic, keywords`

**`keyword-map.csv`** (one row per keyword): `cluster_id, market, keyword, volume, volume_estimated, kd, cpc, is_seed, reader_need, blog_fit, occasion, recipient, interest, product, style, craft, category, market_terms, parent_topic, intent_source, variants, source_file`

Others: `excluded.csv` (keyword, volume, reason, source_file), `unclassified.csv`, `taxonomy-suggestions.csv`, `merge-candidates.csv`, `groups.csv/.md`, `cluster-report.md`.

Values: `reader_need` ∈ inspire, choose, how_to, solve, copy_ideas, info, shop. `blog_fit` ∈ high, medium, low (shop = low). `market` ∈ us, uk, all (or another original value).

## topic-map.csv

`pillar_id, pillar_type, pillar_key, pillar_name, role, cluster_id, primary_keyword, planned_slug, post_type, reader_need, cluster_volume, priority_score, bucket, season, market, occasion, recipient, interest, product, craft, keywords, parent_hint, note`

- `role` ∈ pillar, cluster, standalone, skip. `post_type` ∈ pillar-hub, gift-guide, ideas-list, choose-guide, how-to, explainer, copy-ideas, skip.
- `bucket` A/B/C by priority score (top 20% = A, up to 50% = B). `planned_slug` is a proposed slug (not a real URL).

## link-plan.csv

`source_slug, source_keyword, target_slug, link_type, anchor, anchor_alternatives, placement, priority, status, reason`

- `link_type` ∈ to_pillar, from_pillar, sibling, cross_pillar, orphan_fix, related, backlink_old_post.
- `status` ∈ include_in_draft, include_in_draft_target_not_live_yet, existing_verify_present, update_old_post_after_target_live.

## seasonal-plan.csv

`planned_slug, post_type, role, season, market, event_date, publish_new_by, refresh_existing_by, days_to_publish_by, status, note`; `status` ∈ upcoming, due_soon, overdue, no_calendar_rule.

## Markers in a post

| Marker | Meaning |
|---|---|
| `[PRODUCT-SLOT: ...]` (full syntax in the `product-slot` skill) | a place to mention a product; the content team replaces it with a link |
| `[EXPERIENCE: source]` | real first-hand experience, with an internal source that can be verified |
| `[DATA: source]` / `[DATA NEEDED: ...]` | a figure with a source / a figure that is still missing |
| `[LINK: topic]` | an internal link whose target post does not exist yet |
| `[CLAIM-OK: reason; approver; date]` | a claim approved by someone with authority (claims_check skips it) |
