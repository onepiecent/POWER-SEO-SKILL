---
name: keyword-clustering
description: Đọc file CSV keyword export của SEO Specialist (Semrush, Ahrefs, Google Keyword Planner, Search Console, Google Sheets; nhỏ đến hàng trăm nghìn dòng) và gom nhóm từ khóa theo yêu cầu cụ thể (theo dịp lễ, người nhận, sở thích, sản phẩm, ý định người đọc, nhóm tự định nghĩa, SERP overlap), có lọc nhiễu minh bạch, tách US/UK, báo cáo kiểm chứng. Dùng khi người dùng gửi/nhắc file keyword, "gom nhóm từ khóa", "cluster keywords", "phân nhóm", "lọc từ khóa", "keyword map" cho blog Printerval.
---

# Keyword clustering: đọc export thật, gom nhóm theo yêu cầu

Biến một file từ khóa rất rộng thành **cụm** (mỗi cụm = một bài blog) rồi **nhóm** (các cụm theo chiều bạn cần). Giao tiếp tiếng Việt; keyword và nội dung bàn giao giữ nguyên tiếng Anh.

## Quy trình

1. **Nhận file và yêu cầu.** Xác định: thị trường (US/UK), chiều cần gom nhóm, bộ lọc (volume, KD, từ cần loại/giữ), độ mịn mong muốn. Thiếu thì dùng mặc định và nói rõ giả định (xem bảng bên dưới). Chỉ hỏi khi mơ hồ thật sự.
2. **Chạy lần đầu với cấu hình mặc định + yêu cầu:**
   ```bash
   python3 skills/keyword-clustering/scripts/cluster_keywords.py export.csv --out outputs --group-by occasion,recipient
   ```
   Nhiều file / nhiều thị trường: `us.csv::us uk.csv::uk` (file có cột Country thì tự nhận).
3. **Đọc `outputs/cluster-report.md` trước.** Kiểm tra theo thứ tự:
   - *Đầu vào*: encoding/dấu phân cách/dòng tiêu đề có hợp lý không; cột nào được nhận diện; nguồn volume (`volume` thật hay chỉ `impressions` của GSC).
   - *Bộ lọc*: keyword bị loại và lý do. Mở `excluded.csv`, sắp theo volume, xem có loại nhầm không (ví dụ "boots" không còn là retailer; "mama bear shirt" không phải tiếng Tây Ban Nha). Sai thì sửa `assets/noise-rules.json` hoặc tắt `--no-noise-filter`.
   - *Kết quả*: tỷ lệ cụm 1 keyword (>70% nghĩa là ngưỡng quá chặt hoặc dữ liệu đa dạng: thử `--granularity loose`).
   - *Chưa phân loại*: nếu >15% volume, đọc `taxonomy-suggestions.csv` (n-gram thường gặp trong keyword chưa nhận diện) và đề xuất bổ sung taxonomy (xem `references/taxonomy-guide.md`), rồi chạy lại với `--extend-taxonomy`.
4. **Duyệt `merge-candidates.csv`** (cặp cụm gần ngưỡng gộp): đọc từng cặp, quyết định "gộp / tách / để", ghi lại quyết định cho người dùng. Nếu có SERP thật (`serp_urls`) thì tin SERP hơn từ vựng.
5. **Bàn giao** `clusters.csv` + `cluster-report.md` (+ `groups.md` nếu có `--group-by`), kèm: giả định đã dùng, số liệu thật (đọc/loại/cụm), những chỗ cần người quyết định. Bước tiếp: `topic-map`.

## Dịch yêu cầu của SEO Specialist thành tham số

| Họ nói | Tham số |
|---|---|
| "Chỉ thị trường US/UK" / file là của UK | `file.csv::uk` hoặc `--market uk` |
| "Gom theo người nhận / dịp lễ / sở thích / sản phẩm" | `--group-by recipient` (hoặc occasion, interest, product, style, craft) |
| "Gom theo dịp rồi theo người nhận" | `--group-by occasion,recipient` (lồng nhau) |
| "Phân theo ý định người đọc (ý tưởng, how-to, so sánh...)" | `--group-by intent` |
| "Gom theo nhóm của tôi: Family, Work, Pets..." | `--categories categories.json --group-by category` (xem `examples/categories-example.json`) |
| "Chỉ lấy Mother's Day và Father's Day" | `--only occasion=mothers-day,fathers-day` |
| "Chỉ keyword nói về chó/mèo" | `--only interest=dogs,cats` hoặc `--include "\bdogs?\b" --include "\bcats?\b"` (nhiều `--include` = hoặc) |
| "Bỏ keyword brand/đối thủ/free/pdf" | `--exclude "\bfree\b" --exclude "\bpdf\b"` (retailer/brand đã loại mặc định) |
| "Bỏ keyword volume thấp / quá cao / KD > 60" | `--min-volume 100`, `--max-volume 50000`, `--max-kd 60` |
| "Bỏ keyword mua hàng" | `--drop-shop` (mặc định chỉ gắn `blog_fit=low`, không bỏ) |
| "Cụm nhỏ/chi tiết hơn" / "cụm rộng hơn" | `--granularity tight` / `--granularity loose` (hoặc `--sim 0.7`) |
| "File có cột SERP top 10" | cột `serp_urls`; script tự gom theo SERP overlap (`--serp-overlap 4`) |
| "File Ahrefs có Parent Topic" | `--trust-parent-topic` để gộp theo cột này |
| "Cột tên khác" | `--map keyword="Top queries" volume=Impressions` |
| "Tôi muốn lưu cấu hình để chạy lại" | `--request request.json` (xem `examples/request-example.json`) |

**Yêu cầu phức tạp** ("Mother's Day theo người nhận, Father's Day theo sở thích"): chạy nhiều lần, mỗi lần một `--only` và một `--group-by`, ghi vào các thư mục `--out` khác nhau, rồi tổng hợp cho người dùng. Yêu cầu chưa rõ ("gom cho hợp lý"): dùng mặc định, nói rõ đã chọn gì và vì sao.

Facet và giá trị hợp lệ cho `--only/--group-by`: `assets/taxonomy.json`. Giá trị `intent` = `reader_need`: inspire, choose, how_to, solve, copy_ideas, info, shop.

## Định dạng file được hỗ trợ

Tự xử lý: UTF-8, UTF-8 có BOM, **UTF-16 + tab** (Keyword Planner, một số bản Ahrefs), cp1252; dòng mô tả phía trên tiêu đề (Keyword Planner); phân cách `, ; tab |`; số `1,234`, `1.234`, `1K`, `1.2M`, `1K - 10K` (khoảng, đọc cận dưới, đánh dấu ước lượng; đổi bằng `--range-mode mid`), `<10`, `35%`. Chi tiết cột từng công cụ và điểm cần chú ý: `references/export-formats.md`. File `.xlsx`: xuất ra CSV trước (hoặc dùng skill `xlsx`).

## Cách script gom nhóm (để giải thích và kiểm chứng)

- **Chuẩn hóa:** chữ thường, bỏ dấu nháy (`mother's` -> `mothers`), gạch nối -> khoảng trắng, đổi biến thể UK->US để so khớp (mum->mom, personalised->personalized, nan->grandma), bỏ năm (`2026`), bỏ số nhiều đơn giản. Biến thể cùng nghĩa trong cùng thị trường được gộp trước, giữ keyword volume cao nhất.
- **Nhận diện facet** bằng regex trong taxonomy: dịp lễ, sở thích, người nhận, sản phẩm, phong cách, kiến thức; mỗi keyword có `reader_need` và `blog_fit` (shop = `low`: ý định mua hàng thuần túy, để trang bán hàng/team content xử lý).
- **Gom cụm theo hạt giống** (keyword volume cao nhất làm hạt giống): trùng ≥ N URL SERP, hoặc Jaccard có trọng số ≥ ngưỡng (từ như "gift", "ideas", "best" nặng 0.3). Hai keyword chỉ được gộp theo từ vựng khi **cùng thị trường, cùng nhóm ý định (inspire~choose coi như một) và cùng dịp lễ / người nhận (kể cả ngầm hiểu: mother's day -> mom) / sở thích / sản phẩm**.
- **Hiệu năng:** chỉ mục đảo + lọc tiền tố (chính xác, không bỏ sót cặp đạt ngưỡng; giới hạn ~3.000 phần tử mỗi danh sách), nên 150.000 keyword chạy khoảng 1 phút.

**Giới hạn cần nói thẳng:** từ vựng không hiểu đồng nghĩa sâu (hai cách nói khác hẳn của một ý có thể nằm ở hai cụm); `cluster_volume` là tổng volume nên là cận trên; regex facet có thể bỏ sót niche mới (xem `taxonomy-suggestions.csv`); SERP overlap chính xác hơn nhưng cần dữ liệu SERP thật cho từng thị trường.

## Không làm

- Không bịa volume/KD khi file không có; cảnh báo và giải thích hệ quả.
- Không gộp US với UK (SERP khác nhau, từ vựng khác nhau).
- Không loại keyword lặng lẽ: mọi keyword bị loại phải nằm trong `excluded.csv` với lý do.
- Không biến mỗi biến thể keyword thành một bài (scaled content abuse); một cụm = một bài.

## Tài liệu kèm

- `references/export-formats.md`: cột và đặc điểm file Semrush/Ahrefs/Keyword Planner/GSC.
- `references/reader-needs.md`: bảy loại nhu cầu người đọc, quy tắc nhận diện, `blog_fit`.
- `references/taxonomy-guide.md`: mở rộng taxonomy (niche mới, dịp lễ), tạo `categories.json`, quy tắc noise.
- `assets/taxonomy.json`, `assets/noise-rules.json`: cấu hình có thể sửa.
