# CLAUDE.md

Repo này là bộ skill SEO content cho **blog Printerval** (print-on-demand, thị trường US/UK). Đọc `README.md` trước, rồi `skills/printerval-blog-seo/SKILL.md` (điều phối).

## Quy ước làm việc

- Trao đổi với người dùng bằng **tiếng Việt**; mọi nội dung bàn giao (brief, bài, anchor, title) bằng **tiếng Anh** đúng biến thể US hoặc UK.
- Phạm vi là **nội dung blog**. Không audit kỹ thuật, không URL/sitemap, không link tới trang bán hàng (team content gắn qua `[PRODUCT-SLOT]`).
- Không bịa số liệu, review, trải nghiệm, hạn giao hàng, giá. Thiếu thì `[DATA NEEDED: ...]`.
- Mỗi quy tắc ghi mức bằng chứng: **[Google]**, **[Pháp lý]** (không phải tư vấn pháp lý), **[Nghiên cứu]**, **[Quy ước]**. Điểm số và ngưỡng trong script là heuristic nội bộ.
- File CSV của SEO Specialist có thể lớn và bẩn: luôn chạy script và đọc `cluster-report.md` trước khi báo kết quả.

## Lệnh

```bash
python3 -W error::ResourceWarning -m unittest discover -s tests     # 77 test, chạy vài giây
python3 scripts/package_skills.py                                    # dist/<skill>.zip
```

Script chỉ dùng thư viện chuẩn Python 3 (đã thử trên 3.13). Mỗi skill tự đóng gói trong `skills/<tên>/` (SKILL.md, scripts/, references/, assets/); đừng import chéo giữa các skill (ngoại lệ có fallback: `topic-map` tìm `taxonomy.json` của `keyword-clustering` để đặt tên pillar).

## Khi sửa

- Thêm/sửa regex taxonomy hoặc quy tắc nhiễu: chạy test; đọc lại `excluded.csv` trên dữ liệu mẫu.
- Thêm dịp lễ: sửa `OCCASIONS` trong `occasion_calendar.py` và thêm test ngày đối chiếu **lịch thật** (không lấy ngày từ kết quả tìm kiếm, vốn từng sai).
- Frontmatter SKILL.md phải là YAML hợp lệ (không dùng `: ` trong `description`); `tests/test_skills.py` kiểm tra.
- Cập nhật `skills/printerval-blog-seo/references/sources.md` khi dùng nguồn mới và ghi rõ mức xác minh.
