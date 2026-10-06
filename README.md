# POWER-SEO-SKILL: bộ skill SEO content cho blog Printerval

Bộ skill (cho Claude Code / Claude) giúp đội SEO và content của Printerval biến **file từ khóa export rất rộng** thành **kế hoạch nội dung blog** và những bài viết **hữu ích cho người đọc** (thị trường US/UK, bài tiếng Anh), rồi kiểm tra chúng trước khi đăng.

Phạm vi: **nội dung blog**. Không audit kỹ thuật, không làm URL/sitemap (đang được tối ưu riêng), không lập link tới trang bán hàng: team content gắn link sản phẩm qua `[PRODUCT-SLOT]`, blog dẫn sang trang bán hàng một cách tự nhiên.

## Chín skill

| Skill | Việc làm | Đầu ra |
|---|---|---|
| [`printerval-blog-seo`](skills/printerval-blog-seo/SKILL.md) | Điều phối, quy trình, schema dữ liệu, nguồn nghiên cứu | - |
| [`keyword-clustering`](skills/keyword-clustering/SKILL.md) | Đọc export (Semrush, Ahrefs, Keyword Planner, GSC; đến hàng trăm nghìn dòng), lọc nhiễu minh bạch, gom cụm và nhóm **theo yêu cầu** | `clusters.csv`, `cluster-report.md`, `groups.md` |
| [`topic-map`](skills/topic-map/SKILL.md) | Pillar/cluster theo dịp lễ, sở thích, người nhận, kiến thức, cảm hứng; ưu tiên A/B/C; khoảng trống nội dung | `topic-map.csv/.md` |
| [`internal-link-planner`](skills/internal-link-planner/SKILL.md) | Link giữa các bài blog, anchor, bài mồ côi; audit link hiện có | `link-plan.csv`, `link-audit.csv` |
| [`editorial-calendar`](skills/editorial-calendar/SKILL.md) | Ngày lễ US/UK **tính bằng quy tắc**, hạn xuất bản/làm mới bài theo mùa | `seasonal-plan.csv` |
| [`content-brief`](skills/content-brief/SKILL.md) | Brief tiếng Anh cho writer/AI, 7 khung bài (gift guide, how-to...) | `briefs/<slug>.md` |
| [`helpful-content-editor`](skills/helpful-content-editor/SKILL.md) | Soát bài theo tiêu chí hữu ích (rubric 8 chiều + script) | báo cáo, bản sửa |
| [`product-slot`](skills/product-slot/SKILL.md) | Nhắc sản phẩm tự nhiên, bàn giao team content | `slots.csv` |
| [`claims-compliance-check`](skills/claims-compliance-check/SKILL.md) | Cờ claim giao hàng/review/môi trường/sức khỏe/giá và IP theo FTC/CMA/ASA | báo cáo |

## Quy trình

```
CSV của SEO Specialist
  → keyword-clustering → clusters.csv + cluster-report.md   (đọc báo cáo trước)
    → topic-map → topic-map.csv
        ├─ editorial-calendar → seasonal-plan.csv
        ├─ internal-link-planner → link-plan.csv
        └─ content-brief → briefs/*.md → viết bài
              → helpful-content-editor + claims-compliance-check
              → product-slot (team content gắn link) → đăng
```

## Chạy nhanh (Python 3, chỉ thư viện chuẩn; đã thử trên 3.13)

```bash
# 1. Gom nhóm theo yêu cầu: theo dịp lễ rồi người nhận, chỉ US, bỏ keyword volume < 100
python3 skills/keyword-clustering/scripts/cluster_keywords.py examples/synthetic-keywords-us.csv \
    --out outputs --market us --min-volume 100 --group-by occasion,recipient

# hoặc lưu yêu cầu vào file để chạy lại
python3 skills/keyword-clustering/scripts/cluster_keywords.py --request examples/request-example.json

# 2. Pillar/cluster, lịch theo mùa, kế hoạch link, brief cho nhóm ưu tiên A
python3 skills/topic-map/scripts/topic_map.py outputs/clusters.csv --out outputs
python3 skills/editorial-calendar/scripts/occasion_calendar.py --topic-map outputs/topic-map.csv --out outputs
python3 skills/internal-link-planner/scripts/link_plan.py plan outputs/topic-map.csv --out outputs
python3 skills/content-brief/scripts/make_brief.py --topic-map outputs/topic-map.csv \
    --link-plan outputs/link-plan.csv --seasonal-plan outputs/seasonal-plan.csv --bucket A --out outputs/briefs

# 3. Kiểm tra bản nháp
python3 skills/helpful-content-editor/scripts/helpful_check.py draft.md --market us --post-type gift-guide --keyword "mother's day gifts for grandma"
python3 skills/product-slot/scripts/slot_check.py draft.md --post-type gift-guide --export slots.csv
python3 skills/claims-compliance-check/scripts/claims_check.py draft.md --market us
```

`examples/` có dữ liệu **tổng hợp** (không phải số liệu thật) và hai bản nháp mẫu (`draft-weak-demo.md` cố ý nhiều lỗi, `draft-good-demo.md`) để thử.

## Gom nhóm "theo yêu cầu"

SEO Specialist nói yêu cầu bằng lời; skill dịch thành tham số (bảng đầy đủ ở [`keyword-clustering/SKILL.md`](skills/keyword-clustering/SKILL.md)):

| Yêu cầu | Tham số |
|---|---|
| Gom theo người nhận / dịp lễ / sở thích / sản phẩm / ý định người đọc | `--group-by recipient` (`occasion`, `interest`, `product`, `intent`...) |
| Nhóm tự định nghĩa (Family, Pets, Work...) | `--categories categories.json --group-by category` |
| Chỉ vài dịp lễ, bỏ từ khóa, giới hạn volume/KD | `--only occasion=mothers-day`, `--exclude "\bfree\b"`, `--min-volume 100`, `--max-kd 60` |
| Cụm chi tiết hơn / rộng hơn | `--granularity tight` / `loose` |
| US/UK | `us.csv::us uk.csv::uk` hoặc cột Country |
| Niche mới | `--extend-taxonomy extra.json` (xem gợi ý trong `taxonomy-suggestions.csv`) |

Script tự xử lý UTF-16/tab (Keyword Planner), dòng mô tả phía trên tiêu đề, dấu phân cách `, ; tab |`, số kiểu `1K - 10K`, `1.234`; loại keyword nhiễu (retailer, "near me", tiếng Tây Ban Nha...) **kèm lý do** trong `excluded.csv`. 150.000 keyword chạy khoảng 1 phút.

## Triết lý nội dung

1. **Bài hữu ích khi bỏ hết sản phẩm.** Sản phẩm xuất hiện như lời giải cho vấn đề của người đọc.
2. **Giá trị riêng**: kinh nghiệm/dữ liệu thật của Printerval (`[EXPERIENCE]`, `[DATA]`), không "hàng phổ thông". Không bịa trải nghiệm, số liệu, review, hạn giao hàng.
3. **Không sản xuất hàng loạt**: một cụm = một bài, có người duyệt (scaled content abuse).
4. **Trung thực pháp lý**: claim giao hàng, review, môi trường, sức khỏe, giá và IP được gắn cờ cho người/pháp chế quyết định (không phải tư vấn pháp lý).

Mỗi quy tắc trong tài liệu ghi mức bằng chứng: **[Google]**, **[Pháp lý]**, **[Nghiên cứu]**, **[Quy ước]**. Nghiên cứu nguồn chính thống và mức xác minh: [`docs/research-notes.md`](docs/research-notes.md), [`skills/printerval-blog-seo/references/sources.md`](skills/printerval-blog-seo/references/sources.md).

## Cài đặt skill

- **Claude Code trong repo này:** `.claude/skills` là symlink tới `skills/`, nên các skill tự được nhận diện khi mở repo.
- **Claude Code cá nhân / skill dùng chung:** `python3 scripts/package_skills.py --install ~/.claude/skills` (sao chép) hoặc dùng symlink thủ công.
- **claude.ai (tải lên từng skill):** `python3 scripts/package_skills.py` tạo `dist/<skill>.zip`. Lưu ý: `topic-map` đọc `taxonomy.json` của `keyword-clustering` để đặt tên pillar đẹp; khi tải riêng thì tên pillar suy ra từ key (vẫn chạy bình thường).
- Dùng kèm skill có sẵn **`seo-content-vn`** (title/meta, GEO/AIO, ảnh, hreflang) và **`english-grammar-style`**.

## Kiểm thử

```bash
python3 -W error::ResourceWarning -m unittest discover -s tests
python3 tests/make_big_fixture.py 150000 /tmp/big.csv   # thử hiệu năng
```

77 test: đọc file nhiều định dạng, nhận diện facet, gom cụm (đối chiếu từng cặp với chỉ mục tăng tốc), bộ lọc, topic map, kế hoạch/audit link, ngày lễ đối chiếu lịch thật, brief và các bộ kiểm tra.

## Cấu trúc

```
skills/<skill>/SKILL.md, scripts/, references/, assets/   # mỗi skill tự đóng gói
examples/   dữ liệu tổng hợp, request/categories/taxonomy mẫu, bản nháp demo
tests/      unittest + trình sinh dữ liệu lớn
docs/       research-notes.md
scripts/    package_skills.py
```

## Bảo trì

- **Taxonomy** (`skills/keyword-clustering/assets/taxonomy.json`): thêm niche/dịp khi `taxonomy-suggestions.csv` cho thấy keyword chưa phân loại.
- **Quy tắc nhiễu** (`assets/noise-rules.json`) và **danh sách IP** (`claims-compliance-check/assets/ip-watchlist.txt`, chỉ là điểm khởi đầu; pháp chế duy trì danh sách thật).
- **Lịch** (`occasion_calendar.py`, `OCCASIONS`): thêm dịp mới kèm test ngày.
- Quy định và hướng dẫn của Google/FTC/CMA/ASA thay đổi: cập nhật `references/sources.md` và kiểm tra lại trang gốc.
