---
name: internal-link-planner
description: Lập kế hoạch internal link giữa các bài BLOG Printerval (pillar ↔ cluster, bài cùng cụm, link chéo, link ngược từ bài cũ) từ topic-map.csv, gợi ý anchor mô tả, đánh dấu bài mồ côi hoặc ngõ cụt, và audit file link hiện có (export từ Screaming Frog hoặc Ahrefs với cột source, target, anchor). Dùng khi người dùng nói "internal link", "anchor text", "link giữa các bài", "bài mồ côi/orphan", "link ngược bài cũ". Không lập link tới trang bán hàng hay danh mục.
---

# Internal link planner (blog ↔ blog)

Phạm vi: **chỉ link giữa các bài blog**. Link sang sản phẩm do team content gắn qua `[PRODUCT-SLOT]` (skill `product-slot`). URL/sitemap của Printerval đang thay đổi nên kế hoạch dùng **slug dự kiến** (`planned_slug`), không dùng URL thật.

## Hai chế độ

```bash
# 1. Lập kế hoạch từ topic map
python3 skills/internal-link-planner/scripts/link_plan.py plan outputs/topic-map.csv --out outputs
python3 skills/internal-link-planner/scripts/link_plan.py plan outputs/topic-map.csv --published published.csv --out outputs

# 2. Audit file link hiện có (cột source,target,anchor; chấp nhận from/to/anchor text/link text)
python3 skills/internal-link-planner/scripts/link_plan.py audit links.csv --topic-map outputs/topic-map.csv --out outputs
```

`published.csv`: một cột `slug` (hoặc `url`) liệt kê bài đã đăng. Có file này, `status` cho biết link nào **đưa vào bản nháp mới**, link nào **phải cập nhật bài cũ sau khi bài đích lên**, link nào đã tồn tại.

## Quy tắc (có mức bằng chứng)

- Link phải là thẻ `<a href>` crawl được; anchor **mô tả, ngắn, liên quan tới trang đích**; trang quan trọng cần ít nhất một link trỏ tới; link đặt trong ngữ cảnh có ích cho người đọc. **[Google]** (mục SEO link best practices)
- Không có số link "lý tưởng"; quá nhiều link làm loãng từng link. **[Google]**
- Pillar ↔ mọi cluster (bài con link lên pillar bằng anchor chứa chủ đề pillar; pillar link xuống từng cluster); bài cùng cụm link chéo khi liên quan; tối đa 3 sibling mỗi bài, 1 link chéo pillar. **[Quy ước]**
- Mật độ tham khảo 3-5 link ngữ cảnh/1.000 từ; 1-2 link quan trọng nhất ở nửa đầu bài; mỗi URL đích một link mỗi bài; anchor 2-8 từ, đa dạng nhưng **không dùng cùng anchor cho hai URL khác nhau**. **[Quy ước]**
- Nghiên cứu Zyppy (23 triệu link, **tương quan, không phải nhân quả**): trang nhận khoảng 40-44 link trỏ tới có lượt click cao hơn nhiều so với 0-4 link; vượt ~45-50 thì hiệu ứng đảo chiều; trang mồ côi gần như không có traffic organic. Script chỉ dùng ngưỡng ~50 để **gắn cờ xem lại**. **[Nghiên cứu]**
- Khi đăng bài mới: cập nhật 2-5 bài cũ cùng chủ đề để link tới bài mới (`backlink_old_post`). **[Quy ước]**

## Luồng làm việc

1. Chạy `plan`; đọc `link-summary.md`: số link theo loại, bài mồ côi/ngõ cụt, **phần "chưa giải quyết"**.
2. **Không ép link giữa hai bài không liên quan.** Bài không có bài cùng chủ đề để link tự nhiên được liệt kê riêng: đó là khoảng trống nội dung (cần thêm bài cùng chủ đề), hoặc để người biên tập quyết định.
3. Khi viết bài, đưa cho writer bảng `anchor → slug đích → vị trí → lý do` của bài đó (đã có trong `content-brief`). Anchor trong CSV chỉ là **gợi ý**: viết lại cho khớp câu, đúng chính tả thị trường (mum/mom, personalised/personalized).
4. Sau khi có URL thật (khi sitemap ổn định), ánh xạ `planned_slug` → URL. Nếu slug thật khác slug dự kiến (redirect, đổi tên), lập bảng ánh xạ trước khi chạy `audit`.
5. Chạy `audit` định kỳ (site nhỏ hàng quý) với export link của crawler; ưu tiên sửa theo mức: `high` (bài mồ côi, cluster thiếu link lên pillar, pillar thiếu link xuống cluster, anchor chung chung như "click here"), `medium` (ngõ cụt, anchor trùng cho nhiều đích, anchor rỗng), `low` (anchor quá ngắn/dài, link trùng, mật độ cao).

## Cách `audit` khớp bài

So khớp theo **slug cuối đường dẫn** (bỏ `.html/.php`, tham số, chữ hoa); vì vậy URL đã redirect sang slug khác sẽ không khớp. Link tới trang không thuộc blog (sản phẩm, danh mục) vẫn được đếm như một "node" và có thể bị báo mồ côi: lọc export chỉ còn các URL blog trước khi audit.

## Giới hạn

- Kế hoạch dựa trên facet và từ vựng của keyword, chưa đọc nội dung bài thật; sau khi bài được viết, Claude nên đọc bài và đề xuất vị trí chèn link theo ngữ nghĩa.
- Không có dữ liệu crawl nên không biết link nào đã tồn tại trừ khi có `published.csv` hoặc chạy `audit`.
