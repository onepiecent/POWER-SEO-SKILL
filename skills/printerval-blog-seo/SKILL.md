---
name: printerval-blog-seo
description: Orchestrates the Printerval blog SEO skill suite (print-on-demand marketplace, US and UK markets, English content). Use when the user talks about the Printerval blog, keyword export CSV files from SEO specialists (Semrush, Ahrefs, Keyword Planner, Search Console), keyword clustering, pillar and cluster planning, topic maps, internal links between blog posts, content briefs, gift guides, seasonal content calendars (Mother's Day, Christmas), product slots, claim and IP checks, or whether a draft is helpful to readers. Not for technical audits, URLs or sitemaps, or links to product pages.
---

# Printerval Blog SEO: điều phối

Bộ skill này giúp đội SEO/content của Printerval biến một file từ khóa rất rộng thành kế hoạch nội dung blog và những bài viết **hữu ích cho người đọc**, rồi kiểm tra chúng trước khi đăng. Trao đổi với người dùng bằng tiếng Việt; **mọi nội dung bàn giao (brief, bài, anchor, title) bằng tiếng Anh** đúng biến thể thị trường (US = American English, UK = British English).

## Phạm vi và nguyên tắc cố định

1. **Tập trung nội dung.** Không audit kỹ thuật, không làm URL/sitemap (đang được tối ưu riêng, nhiều redirect), không lập link tới trang bán hàng (`/market`, `/c`...). Link giữa **các bài blog** thuộc phạm vi.
2. **Blog dẫn sang trang bán hàng một cách tự nhiên.** Skill không gắn link sản phẩm; writer để `[PRODUCT-SLOT: ...]` mô tả ngữ cảnh, team content thay bằng link thật. Bài phải **vẫn đầy đủ và hữu ích khi bỏ hết slot** (`slot_check.py --strip`).
3. **Không bịa.** Không bịa số liệu, review, "chúng tôi đã test", hạn giao hàng, giá. Thiếu thì để `[DATA NEEDED: ...]`; trải nghiệm thật thì gắn `[EXPERIENCE: nguồn nội bộ]`.
4. **Không sản xuất hàng loạt.** Google coi việc tạo nhiều trang chủ yếu để thao túng xếp hạng, kể cả bằng AI, là *scaled content abuse*. Mỗi bài cần giá trị riêng và có người duyệt. Không tạo trang cho từng biến thể keyword.
5. **Mỗi quy tắc nói rõ mức bằng chứng** (như skill `seo-content-vn`): **[Google]** hướng dẫn chính thức; **[Pháp lý]** FTC/CMA/ASA (không phải tư vấn pháp lý); **[Nghiên cứu]** có dữ liệu, thường là tương quan; **[Quy ước]** thông lệ ngành, ngưỡng heuristic. Pillar/cluster và "topical authority" là **[Quy ước]**, Google không định nghĩa chúng.

## Chọn skill theo tình huống

| Người dùng muốn | Skill | Đầu ra chính |
|---|---|---|
| Đọc và gom nhóm file keyword export (nhỏ đến rất lớn), theo yêu cầu cụ thể | `keyword-clustering` | `clusters.csv`, `cluster-report.md` |
| Dựng pillar/cluster, biết thiếu loại bài nào | `topic-map` | `topic-map.csv/.md` |
| Kế hoạch link giữa các bài blog, hoặc audit link hiện có | `internal-link-planner` | `link-plan.csv`, `link-audit.csv` |
| Lịch xuất bản theo mùa US/UK | `editorial-calendar` | `occasion-calendar.csv`, `seasonal-plan.csv` |
| Brief cho writer/AI | `content-brief` | `briefs/<slug>.md` |
| Soát/viết lại bài cho hữu ích, trung thực, tự nhiên | `helpful-content-editor` | báo cáo + chỉnh sửa |
| Chỗ nhắc sản phẩm trong bài, bàn giao team content | `product-slot` | `slots.csv` |
| Soát claim giá/giao hàng/review/môi trường/IP | `claims-compliance-check` | báo cáo cờ rủi ro |

Dùng kèm skill có sẵn: **`seo-content-vn`** (title/meta, `seo_check.py`, GEO/AIO, ảnh, hreflang) và **`english-grammar-style`** (bắt buộc khi viết hoặc sửa tiếng Anh).

## Quy trình chuẩn

```
file CSV (SEO Specialist)
  └─ keyword-clustering ──► clusters.csv + cluster-report.md   (đọc báo cáo trước, xử lý cảnh báo, chạy lại nếu cần)
       └─ topic-map ──► topic-map.csv (pillar, cluster, độ ưu tiên, khoảng trống)
            ├─ editorial-calendar ──► seasonal-plan.csv (ngày xuất bản bài theo mùa)
            ├─ internal-link-planner ──► link-plan.csv
            └─ content-brief ──► briefs/*.md   (điền phần [TO FILL] sau khi xem SERP thật)
                 └─ viết bài ──► helpful-content-editor + claims-compliance-check
                      └─ product-slot (bàn giao) ──► team content gắn link ──► đăng (--final)
```

Lệnh mẫu (chạy từ thư mục gốc repo; mọi script chỉ dùng thư viện chuẩn của Python 3):

```bash
python3 skills/keyword-clustering/scripts/cluster_keywords.py export.csv --out outputs --group-by occasion,recipient
python3 skills/topic-map/scripts/topic_map.py outputs/clusters.csv --out outputs
python3 skills/editorial-calendar/scripts/occasion_calendar.py --topic-map outputs/topic-map.csv --out outputs
python3 skills/internal-link-planner/scripts/link_plan.py plan outputs/topic-map.csv --out outputs
python3 skills/content-brief/scripts/make_brief.py --topic-map outputs/topic-map.csv \
    --link-plan outputs/link-plan.csv --seasonal-plan outputs/seasonal-plan.csv --bucket A --out outputs/briefs
```

Schema các file CSV: `references/data-contracts.md`. Nguồn và mức xác minh: `references/sources.md`. Giả định về Printerval và câu hỏi còn mở: `references/printerval-context.md`.

## Cách làm việc với SEO Specialist

- **File thường lớn, bẩn, mỗi công cụ một kiểu.** Chạy script, **đọc `cluster-report.md` trước khi nói gì về kết quả**: số dòng đọc được, encoding, cột nào được nhận diện, keyword bị loại và lý do, tỷ lệ chưa phân loại, cảnh báo.
- Yêu cầu của họ ("gom theo người nhận", "bỏ keyword brand", "chỉ US", "volume từ 200") được dịch thành tham số theo bảng trong `keyword-clustering/SKILL.md`. Nêu giả định đã dùng. Chỉ hỏi lại khi yêu cầu mơ hồ thật sự, tối đa 1-2 câu, kèm đề xuất mặc định.
- Kết quả là **bản nháp có kiểm chứng**, không phải sự thật cuối cùng: cụm gom bằng từ vựng cần Claude/SEO duyệt `merge-candidates.csv`; nếu có SERP overlap (cột `serp_urls`) thì tin SERP hơn.
- Không nói "xong" khi chưa chạy script và đọc đầu ra. Báo cáo trung thực: lệnh nào chạy, số liệu thật, chỗ nào chưa chắc.

## Giới hạn cần nói với người dùng

- Điểm của `helpful_check.py` và điểm ưu tiên của `topic-map` là **heuristic nội bộ**, không phải số đo của Google.
- `cluster_volume` là tổng volume các keyword trong cụm, là cận trên (cùng một nhóm người tìm bằng nhiều cách).
- Lead time xuất bản theo mùa (12 tuần bài mới, 6 tuần cập nhật) là quy ước ngành; hãy hiệu chỉnh bằng GSC/Google Trends của chính site.
- Danh sách IP/nhãn hiệu chỉ là điểm khởi đầu; claim rủi ro cao (sức khỏe, môi trường, giao hàng, review) cần pháp chế/bộ phận liên quan xác nhận.
