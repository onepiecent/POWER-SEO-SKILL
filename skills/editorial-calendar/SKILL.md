---
name: editorial-calendar
description: Computes US and UK holiday dates by rule (US Mother's Day versus UK Mothering Sunday, Father's Day, Thanksgiving, Black Friday, Easter, Halloween, Bonfire Night) and plans publish and refresh deadlines for seasonal blog posts from the topic map. Use when the user mentions a content calendar, seasonal posts, when to publish Mother's Day or Christmas content, or US and UK holiday dates.
---

# Editorial calendar theo mùa (US/UK)

## Chạy

```bash
python3 skills/editorial-calendar/scripts/occasion_calendar.py --year 2027 --market both --out outputs
python3 skills/editorial-calendar/scripts/occasion_calendar.py --topic-map outputs/topic-map.csv --out outputs    # thêm seasonal-plan.csv
python3 skills/editorial-calendar/scripts/occasion_calendar.py --today 2026-10-06 --lead-new 16 --lead-refresh 8 ...
```

Đầu ra: `occasion-calendar.csv/.md` (mọi dịp, hai thị trường) và `seasonal-plan.csv` (mỗi bài có `season` trong topic-map: ngày sự kiện kế tiếp, `publish_new_by`, `refresh_existing_by`, `days_to_publish_by`, `status`).

## Điều cần nhớ

1. **Ngày được TÍNH bằng quy tắc, không lấy từ kết quả tìm kiếm.** Trong lúc nghiên cứu, công cụ tìm kiếm trả sai ngày Mothering Sunday và Father's Day của Anh; script có test đối chiếu (xem `tests/`). Không tự gõ ngày vào bài.
2. **US và UK khác nhau:** Mother's Day US = Chủ nhật thứ hai của tháng 5; Mothering Sunday UK = 3 tuần trước Easter (tháng 3 hoặc 4). Father's Day cùng quy tắc (Chủ nhật thứ ba của tháng 6). Thanksgiving, Fourth of July chỉ US; Bonfire Night chỉ UK. Mỗi thị trường là một dòng riêng, một bài riêng khi cần.
3. **Lead time là quy ước, không phải luật của Google.** Mặc định 12 tuần cho bài mới, 6 tuần cho cập nhật bài cũ (Google không công bố thời gian index/xếp hạng). Hiệu chỉnh bằng seasonality thật: Search Console (impressions theo tuần của các bài mùa năm trước) và Google Trends. Cửa sổ "graduation", "back to school" chỉ **xấp xỉ**.
4. **Một URL theo mùa, làm mới hằng năm.** Giữ nguyên bài pillar/guide theo dịp, cập nhật nội dung và chỉ đổi ngày hiển thị khi nội dung thật sự thay đổi (Google khuyến nghị không làm mới ngày giả; ngày hiển thị khớp structured data). Không tạo `...-2027`.
5. **Không hứa giao hàng.** Bài theo mùa rất hay nhắc "đặt trước ngày X". Hạn đặt hàng/giao hàng chỉ lấy từ bộ phận vận hành kèm ngày xác nhận (`[DATA NEEDED: ...]`), vì quy tắc FTC Mail/Internet Order Merchandise yêu cầu cơ sở hợp lý cho thời gian giao hàng đã nêu và CMA/ASA yêu cầu chứng minh được. Cột `notes` đã nhắc điều này cho Valentine's, Mother's/Father's Day, Christmas.
6. **Bối cảnh nhu cầu (Mỹ):** khảo sát NRF 2026 (qua tóm tắt tìm kiếm, kiểm tra lại trang gốc trước khi trích) cho thấy chi tiêu Mother's Day, Valentine's, Halloween đều ở mức kỷ lục và mua online là điểm mua hàng đầu cho nhiều dịp. Đó là lý do ưu tiên bài theo mùa, không phải bằng chứng về xếp hạng.

## Đọc `seasonal-plan.csv`

| `status` | Nghĩa | Việc làm |
|---|---|---|
| `upcoming` | hạn đăng bài mới còn > 14 ngày | lên lịch theo `publish_new_by` |
| `due_soon` | hạn trong 14 ngày | ưu tiên ngay |
| `overdue` | hạn đăng bài mới đã qua nhưng sự kiện chưa tới | đăng sớm nhất có thể **hoặc** làm mới bài đã có (`refresh_existing_by`) và dồn nguồn lực cho bài bucket A |
| `no_calendar_rule` | `season` chưa có quy tắc ngày | thêm vào `OCCASIONS` trong script hoặc đặt ngày thủ công |

Sự kiện đã qua trong năm nay: script tự chuyển sang lần xuất hiện kế tiếp (năm sau). Thêm dịp mới: sửa `OCCASIONS` (quy tắc `fixed`, `nth`, `easter`, `after`, `window`) và thêm test đối chiếu ngày thật.

## Không có trong script

Bank holiday của Anh (có quy tắc "ngày bù" phức tạp): lấy từ https://www.gov.uk/bank-holidays. Remembrance và các dịp nhạy cảm không đưa vào lịch quà tặng. Xem ghi chú từng dịp ở `references/occasions.md`.
