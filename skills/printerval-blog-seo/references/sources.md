# Nguồn và mức xác minh

Nghiên cứu thực hiện ngày **2026-10-06**. Môi trường làm việc chặn truy cập trực tiếp tới `developers.google.com`, `ftc.gov`, `gov.uk`... (egress proxy), nên các nguồn dưới đây được xác nhận qua **bản tóm tắt kết quả tìm kiếm của chính trang chính thức**, không phải đọc nguyên văn trang. Vì vậy:

- Mức **S** = nội dung được xác nhận qua tóm tắt tìm kiếm của trang chính thức trong phiên này. Trích nguyên văn hoặc dùng cho quyết định pháp lý thì **mở trang gốc và đọc lại**.
- Mức **K** = từ kiến thức nền, chưa kiểm chứng lại trong phiên này.
- Quy định và hướng dẫn thay đổi thường xuyên; trước khi dựa vào một điều khoản, hãy kiểm tra trang gốc.

## Google Search (chính thức)

| Chủ đề | URL | Điều dùng trong bộ skill | Mức |
|---|---|---|---|
| Nội dung hữu ích, đáng tin, ưu tiên con người | https://developers.google.com/search/docs/fundamentals/creating-helpful-content | Câu hỏi tự đánh giá (thông tin gốc, mô tả đầy đủ, phân tích vượt điều hiển nhiên; nguồn, chuyên môn); khung Who/How/Why; E-E-A-T với **trust là quan trọng nhất** | S |
| Hướng dẫn về nội dung do AI tạo | https://developers.google.com/search/docs/fundamentals/using-gen-ai-content | AI hữu ích khi nghiên cứu/dựng cấu trúc; tạo nhiều trang không thêm giá trị có thể vi phạm *scaled content abuse*; phải kiểm chứng sự thật; nên nói rõ cách tạo nội dung. Cập nhật 1/10/2026 dẫn tới Quality Rater Guidelines mục 4.6.5 (scaled content abuse) và 4.6.6 (nội dung ít công sức/độc đáo/giá trị) | S |
| Chính sách spam | https://developers.google.com/search/docs/essentials/spam-policies | Định nghĩa scaled content abuse; site reputation abuse | S |
| Cập nhật chính sách site reputation (28/8/2026) | https://developers.google.com/search/blog/2026/08/update-site-reputation-policy | Trang bên thứ ba/tài trợ/đối tác độc lập với mục đích chính của site hoặc thiếu giám sát chặt có thể bị xử lý; bài của seller/khách mời cần được biên tập kiểm soát | S |
| Tối ưu cho tính năng AI tạo sinh (5/2026) | https://developers.google.com/search/docs/fundamentals/ai-optimization-guide , https://developers.google.com/search/blog/2026/05/a-new-resource-for-optimizing | Nội dung độc đáo/không "hàng phổ thông" ảnh hưởng nhiều nhất; điều kiện hiển thị: được index và đủ điều kiện hiện snippet; không cần file/markup riêng cho AI | S |
| Viết review sản phẩm chất lượng | https://developers.google.com/search/docs/specialty/ecommerce/write-high-quality-reviews | Bằng chứng trải nghiệm, số đo, ưu và nhược điểm, giải thích vì sao "tốt nhất" | S |
| Ngày hiển thị (byline date) | https://developers.google.com/search/docs/appearance/publication-dates | Không làm mới ngày giả; ngày hiển thị khớp structured data | S |
| Google Discover | https://developers.google.com/search/docs/appearance/google-discover | Không clickbait; tiêu đề nêu đúng nội dung; ảnh rộng tối thiểu 1.200 px | S |
| Báo cáo Generative AI trong Search Console (3/6/2026) | https://developers.google.com/search/blog/2026/06/gen-ai-performance-reports | Công cụ đo hiển thị trong tính năng AI | S |
| Hệ thống xếp hạng | https://developers.google.com/search/docs/appearance/ranking-systems-guide | "Helpful content system" đã chuyển sang mục lưu trữ (đã gộp vào xếp hạng lõi): không hứa "phục hồi HCU", vẫn áp dụng hướng dẫn nội dung hữu ích | S |
| Quality Rater Guidelines (tổng quan) | https://services.google.com/fh/files/misc/hsw-sqrg.pdf | Thang chất lượng trang; trust quan trọng nhất; nội dung tạo tự động ít giá trị có thể bị xếp thấp nhất | S (qua nguồn thứ cấp) |
| Link crawl được, anchor mô tả | https://developers.google.com/search/docs/crawling-indexing/links-crawlable | Quy tắc anchor và internal link | K (có trong skill seo-content-vn) |

**Điều Google KHÔNG nói:** Google không định nghĩa "pillar/cluster" hay "topical authority", không đưa độ dài lý tưởng, không công bố thời gian index/xếp hạng. Các ngưỡng tương ứng trong skill này là **[Quy ước]**.

## Hoa Kỳ

| Chủ đề | URL | Điều dùng | Mức |
|---|---|---|---|
| FTC: quy tắc Consumer Reviews and Testimonials (16 CFR Part 465), hiệu lực 21/10/2024 | https://www.ftc.gov/legal-library/browse/federal-register-notices/16-cfr-part-465-trade-regulation-rule-use-consumer-reviews-testimonials-final-rule , https://www.ftc.gov/business-guidance/resources/consumer-reviews-testimonials-rule-questions-answers | Cấm review/testimonial giả (kể cả do AI tạo), mua review, review nội bộ không công bố quan hệ, trang "review độc lập" do công ty kiểm soát, ngăn chặn review | S |
| FTC: Endorsements, Influencers, and Reviews | https://www.ftc.gov/business-guidance/advertising-marketing/endorsements-influencers-reviews | Công bố quan hệ vật chất (trang tồn tại; nội dung chi tiết chưa xác nhận qua tóm tắt trong phiên này) | K |
| FTC: Mail, Internet, or Telephone Order Merchandise Rule | https://www.ftc.gov/business-guidance/resources/business-guide-ftcs-mail-internet-or-telephone-order-merchandise-rule | Phải có cơ sở hợp lý cho thời gian giao hàng đã nêu; nếu không nêu thì 30 ngày; trễ phải xin đồng ý/hủy hoàn tiền | S |
| FTC: Green Guides | https://www.ftc.gov/business-guidance/resources/environmental-claims-summary-green-guides | Không dùng claim "eco-friendly" chung chung không kèm giới hạn; claim recycled/recyclable cần điều kiện | S |
| FTC: chuẩn "Made in USA" | https://www.ftc.gov | "Gần như toàn bộ" sản phẩm sản xuất tại Mỹ | K |
| USPTO: nhãn hiệu, nguy cơ nhầm lẫn | https://www.uspto.gov/trademarks/search/likelihood-confusion | Nhãn hiệu không cần giống hệt mới gây nhầm lẫn | S |
| Plain language (Liên bang) | https://www.plainlanguage.gov | Câu chủ động, từ ngắn, ví dụ; cơ sở cho ngưỡng độ đọc | S |
| NRF: dữ liệu kỳ nghỉ và mua sắm | https://nrf.com/research-insights/holiday-data-and-trends/mothers-day (và các trang Valentine's, Halloween) | Bối cảnh nhu cầu theo mùa ở Mỹ (khảo sát ý định tiêu dùng). Con số 2026 qua tóm tắt tìm kiếm: Mother's Day dự kiến ~$38 tỷ, Valentine's ~$29,1 tỷ, Halloween ~$13,5 tỷ, mua online chiếm 33-38% điểm mua. **Kiểm tra lại trên trang gốc trước khi trích dẫn** | S |

## Vương quốc Anh

| Chủ đề | URL | Điều dùng | Mức |
|---|---|---|---|
| CMA: hướng dẫn review giả (CMA208) và thực hành thương mại không công bằng (CMA207); DMCC Act 2024 | https://www.gov.uk/government/publications/unfair-commercial-practices-cma207/unfair-commercial-practices | Từ 4/2025: review giả và review khuyến khích không công bố là hành vi bị cấm; trình bày thông tin review gây hiểu lầm | S |
| CMA: Green Claims Code | https://greenclaims.campaign.gov.uk/ | 6 nguyên tắc: trung thực, rõ ràng, không giấu thông tin quan trọng, so sánh công bằng, xét vòng đời sản phẩm | S |
| ASA: phạm vi với website của nhà quảng cáo | https://www.asa.org.uk/advice-online/remit-own-websites.html | Từ 2011 CAP Code áp dụng cho nội dung trên website của chính nhà quảng cáo nếu gắn trực tiếp với việc cung cấp hàng hóa; một số bài blog "không rõ ràng nhằm bán hàng" có thể là nội dung biên tập | S |
| GOV.UK style guide (plain English) | https://www.gov.uk/guidance/style-guide/a-to-z | Câu ngắn, từ đơn giản, chủ động; cơ sở cho chính tả/giọng văn UK | S |
| UK IPO: nhãn hiệu | https://www.gov.uk/how-to-register-a-trade-mark | Nhãn hiệu UK bị từ chối nếu trùng/giống nhãn hiệu có trước | S |
| Ngày nghỉ lễ ngân hàng | https://www.gov.uk/bank-holidays | Nguồn chính thức cho bank holiday (script lịch KHÔNG tính bank holiday) | S |

## Lưu ý đã gặp khi nghiên cứu

- **Kết quả tìm kiếm có thể sai về ngày lễ.** Tóm tắt tìm kiếm trả về "Mothering Sunday 2026 là 19/3" và "Father's Day 2026 là thứ Tư 21/6", cả hai đều sai (Mothering Sunday 2026 là Chủ nhật 15/3; Father's Day 2026 là Chủ nhật 21/6). Vì vậy `occasion_calendar.py` **tính ngày bằng quy tắc** và có test đối chiếu.
- Con số tự công bố của Printerval và dữ liệu Semrush qua snippet không đồng nhất; không dùng làm bằng chứng.
- Ngưỡng độ đọc (Flesch-Kincaid ≤ 10), mật độ link (3-5 / 1.000 từ), ngưỡng ~50 link trỏ tới (Zyppy, tương quan) là **[Quy ước]/[Nghiên cứu tương quan]**.
