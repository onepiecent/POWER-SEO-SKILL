---
name: topic-map
description: Builds a pillar and cluster map for the Printerval blog from clusters.csv (the output of keyword-clustering). Chooses pillars by occasion, interest, recipient, know-how (sizing, washing, printing) and inspiration (slogans, captions), ranks posts A, B or C, shows content gaps, and removes pure shopping keywords from the blog plan. Use when the user mentions pillars, clusters, a topic map, a blog content plan, or which posts to write first.
---

# Topic map: pillar/cluster

Nhận `clusters.csv`, trả `topic-map.csv` (cho máy) và `topic-map.md` (cho người). Mỗi **cụm = một bài**; bài **pillar** là trang tổng hợp chủ đề; bài **cluster** là bài chi tiết thuộc pillar. Pillar/cluster và "topical authority" là **[Quy ước]** của ngành, không phải khái niệm của Google: đừng hứa kết quả xếp hạng chỉ vì có cấu trúc này.

## Chạy

```bash
python3 skills/topic-map/scripts/topic_map.py outputs/clusters.csv --out outputs
python3 skills/topic-map/scripts/topic_map.py outputs/clusters.csv --priority occasion,interest,recipient,craft --min-clusters 3
```

## Cách chọn pillar (giải thích được)

Gán theo từng **tầng** ưu tiên (mặc định `occasion,interest,recipient,craft`, rồi `inspiration`, `product`). Ở mỗi tầng, các cụm có cùng giá trị facet (ví dụ `occasion=mothers-day`) tạo một pillar **nếu có ≥ `--min-clusters` cụm** (mặc định 3); cụm chưa được nhận thì rơi xuống tầng sau. Cụm không tầng nào nhận là `standalone` (kèm `parent_hint` nếu có pillar liên quan).

- Bài kiến thức (how-to, solve, info về giặt/size/in ấn) luôn vào pillar `craft`, không vào pillar theo đối tượng.
- Người nhận quá rộng ("her", "him") không lập pillar.
- Pillar page = cụm "list" (inspire/choose) có volume lớn nhất và ít facet phụ nhất; không có thì tạo **pillar ảo** (chủ đề chưa có bài đầu mối: cần nghiên cứu keyword đầu mối rồi viết như một hub).
- Cụm `blog_fit=low` (ý định mua hàng) → `role=skip`, không viết blog.
- Tầng thêm: `--priority category,occasion` dùng nhóm tự định nghĩa (`--categories` ở bước gom nhóm).

**Điểm ưu tiên** = `cluster_volume` × trọng số blog fit (1 / 0.6 / 0.15) × (0.5 + khả thi), khả thi = 1 − KD/100 (thiếu KD = 0.5). Bucket **A** = 20% đầu, **B** đến 50%, còn lại **C**. Đây là heuristic để xếp việc (ma trận giá trị × khả thi), không phải dự báo traffic.

## Đọc và kiểm tra đầu ra

1. Mở `topic-map.md`: mỗi pillar có bảng cụm, loại bài, ưu tiên và dòng **Khoảng trống nội dung** (thiếu gift guide theo người nhận, thiếu slogan/caption/lời nhắn thiệp, thiếu how-to...). Đó là danh sách nghiên cứu keyword bổ sung, không phải lệnh viết bài.
2. Soát tay các điểm sau và nói với người dùng:
   - Pillar nào nên gộp hoặc tách (ví dụ hai pillar sở thích gần nhau; pillar quá 30 cụm cần chia hub con).
   - Cụm `info` volume lớn nhưng chỉ là câu trả lời ngắn: nên là một mục trong pillar thay vì bài riêng.
   - Cụm có nguy cơ **cannibalization** (hai cụm gần nhau về ý định): xem `merge-candidates.csv` của bước gom nhóm.
   - Cụm theo mùa (`season`): chuyển sang `editorial-calendar`.
3. Bàn giao cho người dùng: số pillar/cụm/standalone/skip, top bài bucket A, khoảng trống, các quyết định cần họ chốt.

## Bước tiếp theo

`editorial-calendar` (ngày xuất bản bài theo mùa) → `internal-link-planner` (link giữa các bài) → `content-brief` (brief cho bucket A).

## Giới hạn

- Slug (`planned_slug`) là slug dự kiến sinh từ keyword, **không phải URL thật**; URL/sitemap của Printerval đang được tối ưu riêng.
- Facet lấy từ regex trong taxonomy: niche chưa có trong taxonomy sẽ thành standalone hoặc chưa phân loại (xem `keyword-clustering/references/taxonomy-guide.md`).
- Với dữ liệu ít (vài chục cụm), ít pillar đạt ngưỡng 3 cụm là bình thường; giảm `--min-clusters 2` khi cần nhưng đừng tạo pillar mỏng chỉ để có cấu trúc.

Tài liệu kèm: `references/pillar-types.md` (loại pillar, tên gọi, độ phủ kỳ vọng, cách viết trang hub).
