---
name: content-brief
description: Generates and completes English content briefs for the Printerval blog from the topic map (metadata, keywords, outline by post type such as gift guide, ideas list, choose guide, how-to, explainer, copy ideas or pillar hub, internal links, product slot plan, compliance flags, publish deadline). Use when the user needs a brief, an outline, help preparing an article or a hand-off to writers, or after a topic map or link plan exists.
---

# Content brief

Brief là **hợp đồng chất lượng** giữa SEO và người viết: người đọc cần gì, bài phải có gì, điều gì khiến bài khác biệt, không được làm gì. Script điền phần có thể tính toán; Claude/SEO điền phần cần xem SERP thật và phần kinh nghiệm thật của Printerval.

## Quy trình

1. **Sinh khung:**
   ```bash
   python3 skills/content-brief/scripts/make_brief.py --topic-map outputs/topic-map.csv \
       --link-plan outputs/link-plan.csv --seasonal-plan outputs/seasonal-plan.csv --bucket A --limit 10 --out outputs/briefs
   python3 skills/content-brief/scripts/make_brief.py --topic-map outputs/topic-map.csv --slug mothers-day-gifts-for-grandma
   ```
2. **Điền các mục `[TO FILL]`** (xem `references/serp-review.md`):
   - Người đọc là ai, tình huống nào; điều gì khiến họ đóng tab thất vọng.
   - SERP thật trên google.com (US) hoặc google.co.uk (UK), **không tìm từ IP Việt Nam**: định dạng đang thắng, đối thủ làm tốt gì và **thiếu gì** (khoảng trống nội dung), câu hỏi trong People Also Ask/AI Overview cần trả lời **trong cùng một bài** (không tách thành trang mỏng).
   - **Góc kinh nghiệm thật**: hỏi các câu trong mục "First-hand angle" với đúng bộ phận (support, thiết kế, QC, vận hành); ghi `[EXPERIENCE: nguồn]` hoặc `[DATA: nguồn]`. Thiếu thì ghi rõ "chưa có" và nói với người dùng; **không bịa**.
   - Nguồn cần trích (ưu tiên nguồn gốc: .gov/.gov.uk, tổ chức tiêu chuẩn, khảo sát có thể kiểm chứng, tài liệu của team sản phẩm).
   - Title/meta 2-3 phương án; đo bằng `seo-content-vn/scripts/seo_check.py`.
3. **Kiểm tra brief** trước khi giao: có ít nhất một nguồn kinh nghiệm/dữ liệu gốc khả thi? cờ tuân thủ đã đọc? link nội bộ khớp kế hoạch? thị trường và biến thể tiếng Anh đúng?
4. **Giao cho writer/AI** cùng skill `helpful-content-editor` (tiêu chí hữu ích), `product-slot` (cách nhắc sản phẩm) và `english-grammar-style` (biên tập tiếng Anh).

## Khung bài theo loại (`assets/formats/`)

| `post_type` | Khi dùng | Đặc trưng |
|---|---|---|
| gift-guide | quà theo dịp/người nhận/sở thích | nhóm theo lý do/tính cách; mỗi ý tưởng có lý do hợp, ưu/nhược; không giá cố định |
| ideas-list | ý tưởng không gắn quà | chất lượng hơn số lượng; mỗi mục có chi tiết phân biệt |
| choose-guide | X vs Y, best X, cách chọn | kết luận trước; tiêu chí; bảng so sánh; nhược điểm; chỉ "đã test" khi thật |
| how-to | cách làm/giải quyết vấn đề | trả lời nhanh trước; bước đánh số; lỗi thường gặp; không hứa kết quả |
| explainer | what is / when is | câu trả lời trực tiếp 2 câu đầu; ngày lễ phải tính, không đoán |
| copy-ideas | slogan, quote, caption, lời nhắn | nội dung gốc; nhóm theo giọng điệu; giới hạn in do team thiết kế |
| pillar-hub | bài tổng hợp chủ đề | "Start here"; tóm tắt từng cluster + một link; làm mới hằng năm |

Mỗi file định dạng có: Skeleton, Rules, **Experience prompts** (câu hỏi phỏng vấn nội bộ), Product-slot guidance. Chúng được chèn vào brief tự động. Kho kinh nghiệm dùng chung: `assets/experience-bank-template.md`.

## Nguyên tắc cho nội dung hữu ích (tóm tắt, chi tiết ở `helpful-content-editor`)

- Trả lời sớm; bài **vẫn hữu ích khi bỏ hết product slot**.
- Có điểm kinh nghiệm hoặc dữ liệu gốc: Google nhấn mạnh nội dung "non-commodity" (góc nhìn riêng, kinh nghiệm trực tiếp), thứ khó thay bằng một bản tóm tắt chung.
- Không viết hàng loạt cho từng biến thể keyword; một cụm = một bài (scaled content abuse).
- Số liệu có nguồn gốc; không tự bịa; ghi `[DATA NEEDED: ...]`.
- Nếu AI hỗ trợ viết nháp: người biên tập kiểm chứng sự thật và thêm giá trị gốc; cân nhắc nói rõ cách tạo nội dung theo cách hợp với người đọc (hướng dẫn của Google).
