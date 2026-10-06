# Đặc điểm file export theo công cụ

`kw_ingest.py` tự nhận diện encoding, dấu phân cách, dòng tiêu đề và tên cột. Bảng dưới là các điển hình hay gặp; tên cột thực tế có thể khác theo phiên bản công cụ, vì vậy luôn đối chiếu bảng "Cột nhận diện" trong `cluster-report.md`.

| Nguồn | Cột thường có | Điểm cần chú ý |
|---|---|---|
| **Semrush** (Keyword Magic Tool, Organic Research) | Keyword, Intent, Volume (hoặc Search Volume), Keyword Difficulty, CPC (USD), Competitive Density, Number of Results, Trend, SERP Features | `Intent` là nhãn của Semrush (có thể nhiều giá trị): chỉ giữ ở `intent_source`, không dùng để gom nhóm. Dữ liệu theo "database" quốc gia đã chọn, thường không có cột country: gán bằng `file.csv::us`. |
| **Ahrefs** (Keywords Explorer, Organic keywords) | Keyword, Country, Difficulty (KD), Volume, CPC, Parent Topic / Parent Keyword, SERP Features, Traffic potential | Có thể xuất UTF-16 hoặc UTF-8 tùy tùy chọn; script tự nhận. `Parent Topic` do Ahrefs tính từ SERP: dùng `--trust-parent-topic` để gộp theo cột này, hoặc để script gợi ý trong `merge-candidates.csv`. Cột Country cho phép tách US/UK tự động. |
| **Google Keyword Planner** | Keyword, Currency, Avg. monthly searches, Three month change, YoY change, Competition, Top of page bid... | Thường là **UTF-16 phân cách tab** đuôi `.csv`, có 1-3 dòng mô tả phía trên tiêu đề (đã xử lý). Tài khoản không chạy quảng cáo thường trả volume dạng **khoảng** ("1K - 10K"): đọc cận dưới và đánh dấu `volume_estimated=1` (đổi bằng `--range-mode mid` hoặc `--range-mode high`). Cột `Competition` là mức cạnh tranh quảng cáo, không phải KD SEO nên không dùng làm KD. |
| **Google Search Console** (Performance, Queries) | Top queries, Clicks, Impressions, CTR, Position | Không có volume thị trường. Script dùng **Impressions** làm volume và **cảnh báo**: đây là nhu cầu mà site đã hiển thị, không phải toàn bộ cơ hội. Dùng GSC để tìm khoảng trống/ cải thiện bài cũ; nên kết hợp với file volume từ công cụ keyword. |
| **Google Sheets / tự tạo** | tùy | Chỉ cần cột keyword. Nếu tên cột khác thường: `--map keyword=<tên cột> volume=<tên cột>`. |
| **Xuất từ API SERP (DataForSEO, SerpAPI...)** | keyword + danh sách URL top 10 | Đưa URL vào cột `serp_urls` (ngăn cách bằng dấu gạch đứng hoặc khoảng trắng). Đây là cách gom cụm **chính xác nhất** (≥4 URL trùng = cùng một bài). Mỗi thị trường cần SERP của chính thị trường đó (google.com cho US, google.co.uk cho UK). |

## Mẹo xử lý file rất lớn

- Đo trên dữ liệu tổng hợp 150.000 keyword: khoảng 45-55 giây, đỉnh RAM khoảng 480 MB (Python 3.13). Ước tính tuyến tính: 500.000 dòng cần khoảng 1,5 GB RAM. File hàng triệu dòng: chia theo thị trường hoặc theo hạt giống trước (ví dụ mỗi seed một file), hoặc lọc `--min-volume` ngay từ đầu. Dữ liệu thật có thể chậm hơn dữ liệu tổng hợp.
- Đa số keyword trong export rộng là nhiễu với blog (retailer, "near me", tiếng Tây Ban Nha...). Bộ lọc mặc định loại chúng **kèm lý do** trong `excluded.csv`; đừng tắt trừ khi có lý do.
- Nhiều file cùng chủ đề: truyền nhiều đường dẫn một lần; keyword trùng được gộp (giữ volume lớn nhất, không cộng dồn giữa các file).

## Khi script báo "Không tìm thấy dòng tiêu đề"

Mở 5 dòng đầu được in ra. Nếu cột keyword có tên lạ, chạy lại với `--map keyword="<tên cột chính xác>"`. Nếu file không có dòng tiêu đề, thêm một dòng `keyword,volume` ở đầu.
