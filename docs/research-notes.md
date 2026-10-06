# Ghi chú nghiên cứu (2026-10-06)

Tài liệu này tóm tắt những gì tìm được từ nguồn chính thống, quyết định thiết kế bắt nguồn từ chúng, và những chỗ chưa chắc. Danh sách nguồn, URL và mức xác minh nằm ở [`skills/printerval-blog-seo/references/sources.md`](../skills/printerval-blog-seo/references/sources.md).

**Giới hạn phương pháp:** môi trường làm việc chặn truy cập trực tiếp tới `printerval.com`, `developers.google.com`, `ftc.gov`, `gov.uk`... nên các điểm dưới đây được xác nhận qua **bản tóm tắt kết quả tìm kiếm của trang chính thức**, không phải đọc nguyên văn. Trước khi trích nguyên văn hoặc dùng cho quyết định pháp lý, hãy mở trang gốc.

## 1. Google: điều thay đổi cách thiết kế

| Phát hiện | Ảnh hưởng thiết kế |
|---|---|
| Hướng dẫn nội dung hữu ích: thông tin gốc, mô tả đầy đủ, phân tích vượt điều hiển nhiên; nguồn, chuyên môn; khung **Who/How/Why**; **trust** là yếu tố quan trọng nhất trong E-E-A-T | Rubric 8 chiều của `helpful-content-editor`; kiểm tra byline/ngày/nguồn; `[EXPERIENCE]`/`[DATA]` bắt buộc cho góc nhìn riêng |
| Hướng dẫn tối ưu cho tính năng AI (5/2026): nội dung **độc đáo, không "hàng phổ thông"** ảnh hưởng nhiều nhất; điều kiện hiển thị chỉ là được index + đủ điều kiện hiện snippet; không cần file/markup riêng cho AI | Không có "mẹo GEO" tùy tiện trong skill; kho kinh nghiệm (`experience-bank`) và pillar `craft` là nơi tạo khác biệt |
| Hướng dẫn nội dung AI (cập nhật 1/10/2026 dẫn tới Quality Rater Guidelines 4.6.5, 4.6.6): AI giúp nghiên cứu/dựng cấu trúc nhưng tạo nhiều trang không thêm giá trị là **scaled content abuse**; phải kiểm chứng sự thật; nên nói cách tạo nội dung; nội dung chính ít công sức/độc đáo/giá trị bị xếp thấp nhất | Mỗi cụm = một bài, không tạo trang theo biến thể keyword; bắt buộc người duyệt; cảnh báo hallucination trong rubric; không có chế độ "sinh hàng loạt" |
| Chính sách **site reputation abuse** (cập nhật 28/8/2026): trang bên thứ ba/tài trợ/đối tác độc lập mục đích chính của site hoặc thiếu giám sát chặt | Bài của seller/khách mời/tài trợ phải được biên tập kiểm soát (ghi trong rubric trust) |
| Hướng dẫn viết review: bằng chứng trải nghiệm, số đo, ưu **và nhược điểm**, giải thích vì sao "tốt nhất" | Khung `gift-guide` và `choose-guide`: mỗi ý tưởng có lý do, nhược điểm; "tested" chỉ khi thật |
| Ngày hiển thị: không làm mới ngày giả; khớp structured data | Bài theo mùa giữ một URL, làm mới hằng năm, chỉ đổi ngày khi nội dung đổi (`editorial-calendar`) |
| Discover: không clickbait, tiêu đề nêu đúng nội dung, ảnh rộng ≥ 1.200 px | Tiêu chí 1 và 8 của rubric |
| "Helpful content system" đã chuyển sang mục lưu trữ của hướng dẫn hệ thống xếp hạng (gộp vào xếp hạng lõi) | Không hứa "phục hồi HCU"; hướng dẫn nội dung hữu ích vẫn là chuẩn tham chiếu |
| Search Console có báo cáo Generative AI (6/2026) | Gợi ý đo hiển thị AI sau khi đăng |

**Google không định nghĩa pillar/cluster hay topical authority**, không công bố độ dài lý tưởng hay thời gian index. Các ngưỡng tương ứng trong skill là **[Quy ước]**.

## 2. Pháp lý và quảng cáo (không phải tư vấn pháp lý)

| Chủ đề | Điểm chính | Rule trong `claims_check.py` |
|---|---|---|
| FTC 16 CFR Part 465 (hiệu lực 21/10/2024) | Cấm review giả (kể cả do AI tạo), mua review theo cảm xúc, review nội bộ không công bố, trang review "độc lập" do công ty kiểm soát | `review_testimonial`, `first_hand_claim` |
| CMA DMCC Act 2024 (từ 4/2025, CMA208) | Review giả/khuyến khích không công bố và trình bày review gây hiểu lầm bị cấm tự thân | `review_testimonial` |
| FTC Mail/Internet Order Merchandise Rule | Có cơ sở hợp lý cho thời gian giao hàng đã nêu; mặc định 30 ngày; trễ thì xin đồng ý | `delivery_promise` |
| FTC Green Guides; CMA Green Claims Code | Không "eco-friendly" chung chung; claim cụ thể cần bằng chứng | `eco_general`, `eco_specific` |
| ASA CAP Code và website của nhà quảng cáo | Nội dung trên website của nhà bán gắn trực tiếp với việc bán hàng có thể thuộc phạm vi CAP; một số bài blog có thể là nội dung biên tập | `uk_remit_note`, `superlative_guarantee` |
| USPTO/UK IPO: nhãn hiệu | Nhầm lẫn nhãn hiệu không cần giống hệt | `ip_brand` |
| FTC "Made in USA", Endorsement Guides | Kiến thức nền (chưa xác minh lại trong phiên) | `made_in`, `disclosure` |

## 3. Dữ liệu nhu cầu theo mùa

Khảo sát NRF 2026 (qua tóm tắt tìm kiếm; **kiểm tra lại trang gốc trước khi trích**): Mother's Day dự kiến ~$38 tỷ (mức kỷ lục), Valentine's ~$29,1 tỷ, Halloween ~$13,5 tỷ; mua online là điểm mua hàng đầu hoặc đồng hạng đầu ở nhiều dịp. Chỉ dùng làm bối cảnh ưu tiên bài theo mùa, không phải bằng chứng xếp hạng.

## 4. Lỗi của kết quả tìm kiếm đã được phát hiện

Tóm tắt tìm kiếm trả "Mothering Sunday 2026 là 19/3" và "Father's Day 2026 là thứ Tư 21/6": **cả hai sai** (Mothering Sunday 2026 là Chủ nhật 15/3; Father's Day 2026 là Chủ nhật 21/6). Vì vậy ngày lễ được **tính bằng quy tắc** và có test đối chiếu lịch thật (`tests/test_pipeline.py`). Bài học: không dùng số liệu/ngày từ tóm tắt tìm kiếm mà không kiểm tra chéo.

## 5. Về Printerval

Không truy cập được `printerval.com` nên không phân tích trực tiếp. Từ kết quả tìm kiếm: marketplace print-on-demand với seller độc lập; URL có nhiều kiểu (`/slug-p<id>`, `/c/...`, `/market/<keyword>`, `/<locale>/`); nhiều tiêu đề sản phẩm do seller nhập, dài và nhồi từ khóa; số liệu tự công bố không nhất quán. Theo yêu cầu của người dùng, URL/sitemap/audit kỹ thuật **ngoài phạm vi**. Giả định và câu hỏi mở: [`printerval-context.md`](../skills/printerval-blog-seo/references/printerval-context.md).

## 6. Những gì chưa làm được / chưa chắc

- Chưa đọc nguyên văn các trang chính thống (bị chặn); mọi ô mức **S** nên được xác nhận lại trước khi dùng cho quyết định lớn.
- Taxonomy (dịp lễ, người nhận, sở thích, sản phẩm) là điểm khởi đầu theo hiểu biết chung về quà tặng/POD, chưa đối chiếu catalog thật của Printerval.
- Ngưỡng heuristic (độ đọc, mật độ link, lead time 12/6 tuần, mật độ slot) là **[Quy ước]**: cần hiệu chỉnh bằng dữ liệu của site.
- Gom cụm bằng từ vựng không hiểu đồng nghĩa sâu; kết quả tốt nhất khi có SERP overlap thật.
- Danh sách IP chỉ là mẫu khởi đầu; cần pháp chế duy trì.
