# Data contracts: schema các file CSV trong pipeline

Mọi file là CSV UTF-8, dòng đầu là tiêu đề. Tên cột cố định để các skill nối với nhau.

## Đầu vào của SEO Specialist (keyword-clustering đọc trực tiếp)

Chỉ cần một cột keyword. Các cột khác được tự nhận diện theo tên (không phân biệt hoa thường, bỏ phần trong ngoặc cuối):

| Cột chuẩn | Tên cột được nhận diện |
|---|---|
| keyword | Keyword, Keywords, Query, Top queries, Search term |
| volume | Volume, Search Volume, Avg. monthly searches, Monthly searches |
| impressions / clicks | Impressions, Clicks (GSC; chỉ dùng làm volume khi không có cột volume, kèm cảnh báo) |
| kd | KD, KD %, Keyword Difficulty, Difficulty |
| cpc | CPC, CPC (USD) |
| market | Market, Country, Location, Geo |
| serp | serp_urls, Top URLs, SERP (các URL top 10, ngăn cách bằng dấu gạch đứng hoặc khoảng trắng) |
| intent | Intent, Intents (chỉ giữ để tham khảo) |
| parent | Parent Topic, Parent Keyword (Ahrefs) |
| position | Position, Avg. position (GSC) |

Cột lạ: `--map keyword="Top queries" volume=Impressions`.

## Đầu ra của keyword-clustering

**`clusters.csv`** (một dòng một cụm = một bài blog): `cluster_id, market, cluster_name, keyword_count, seed_volume, cluster_volume, seed_kd, kd_min, reader_need, blog_fit, occasion, recipient, interest, product, style, craft, category, season, market_terms, parent_topic, keywords`

**`keyword-map.csv`** (một dòng một keyword): `cluster_id, market, keyword, volume, volume_estimated, kd, cpc, is_seed, reader_need, blog_fit, occasion, recipient, interest, product, style, craft, category, market_terms, parent_topic, intent_source, variants, source_file`

Khác: `excluded.csv` (keyword, volume, reason, source_file), `unclassified.csv`, `taxonomy-suggestions.csv`, `merge-candidates.csv`, `groups.csv/.md`, `cluster-report.md`.

Giá trị: `reader_need` ∈ inspire, choose, how_to, solve, copy_ideas, info, shop. `blog_fit` ∈ high, medium, low (shop = low). `market` ∈ us, uk, all (hoặc giá trị gốc khác).

## topic-map.csv

`pillar_id, pillar_type, pillar_key, pillar_name, role, cluster_id, primary_keyword, planned_slug, post_type, reader_need, cluster_volume, priority_score, bucket, season, market, occasion, recipient, interest, product, craft, keywords, parent_hint, note`

- `role` ∈ pillar, cluster, standalone, skip. `post_type` ∈ pillar-hub, gift-guide, ideas-list, choose-guide, how-to, explainer, copy-ideas, skip.
- `bucket` A/B/C theo điểm ưu tiên (20% đầu = A, đến 50% = B). `planned_slug` là slug dự kiến (không phải URL thật).

## link-plan.csv

`source_slug, source_keyword, target_slug, link_type, anchor, anchor_alternatives, placement, priority, status, reason`

- `link_type` ∈ to_pillar, from_pillar, sibling, cross_pillar, orphan_fix, related, backlink_old_post.
- `status` ∈ include_in_draft, include_in_draft_target_not_live_yet, existing_verify_present, update_old_post_after_target_live.

## seasonal-plan.csv

`planned_slug, post_type, role, season, market, event_date, publish_new_by, refresh_existing_by, days_to_publish_by, status, note`; `status` ∈ upcoming, due_soon, overdue, no_calendar_rule.

## Marker trong bài viết

| Marker | Ý nghĩa |
|---|---|
| `[PRODUCT-SLOT: ...]` (cú pháp đầy đủ ở skill `product-slot`) | chỗ nhắc sản phẩm, team content thay bằng link |
| `[EXPERIENCE: nguồn]` | trải nghiệm thật, có nguồn nội bộ kiểm chứng được |
| `[DATA: nguồn]` / `[DATA NEEDED: ...]` | số liệu có nguồn / số liệu còn thiếu |
| `[LINK: chủ đề]` | chỗ link nội bộ chưa có bài đích |
| `[CLAIM-OK: lý do; người duyệt; ngày]` | claim đã được người có thẩm quyền duyệt (claims_check bỏ qua) |
