---
name: helpful-content-editor
description: Soát, chấm và biên tập bài blog tiếng Anh (US/UK) của Printerval theo tiêu chí nội dung hữu ích cho người đọc (people-first), gồm trả lời sớm, góc nhìn và kinh nghiệm thật, bằng chứng, trung thực, dễ đọc, nhắc sản phẩm tự nhiên, không viết cho công cụ tìm kiếm trước, bớt giọng AI. Dùng khi người dùng gửi bản nháp hoặc nói "review bài", "bài này đã hữu ích chưa", "chấm bài", "sửa cho tự nhiên", "E-E-A-T", "bớt giọng AI", "helpful content".
---

# Helpful content editor

Kiểm tra bản nháp bằng **hai lớp**: script đo phần đo được; Claude đánh giá phần cần phán đoán theo `references/rubric.md`. Kết quả cuối là danh sách sửa theo mức tác động, và bản sửa nếu người dùng yêu cầu. Giao tiếp tiếng Việt; **văn bản tiếng Anh được sửa trực tiếp** theo biến thể US/UK, kèm skill `english-grammar-style`.

## Quy trình

1. **Xác định bối cảnh:** thị trường (US/UK), `post_type` (gift-guide, ideas-list, choose-guide, how-to, explainer, copy-ideas, pillar-hub), từ khóa chính, có brief không.
2. **Chạy script:**
   ```bash
   python3 skills/helpful-content-editor/scripts/helpful_check.py draft.md --market us --post-type gift-guide --keyword "mother's day gifts for grandma"
   python3 skills/helpful-content-editor/scripts/helpful_check.py final.md --final     # trước khi đăng: placeholder = lỗi
   ```
   Script đo: cấu trúc (1 H1, H2 theo mục), độ dài mở bài, độ đọc (Flesch-Kincaid, câu dài, bị động), câu có số liệu không nguồn, câu "we tested" không có bằng chứng, cụm sáo rỗng/giọng AI, nhồi từ khóa, CTA bán hàng, tín hiệu tin cậy (tác giả, ngày), chính tả/định dạng US-UK, placeholder.
3. **Đọc bài như người đọc** rồi chấm theo `references/rubric.md` (8 chiều, 0-3 điểm mỗi chiều, kèm dấu hiệu đỏ). Phần Claude phải tự đánh giá, script không làm được: có góc nhìn riêng chưa, bao phủ đủ câu hỏi tiếp theo của người đọc chưa, có trung thực không, sản phẩm có đang chen vào không.
4. **Lập danh sách sửa**, tối đa ~7 mục, xếp theo tác động: (1) sự thật/trung thực, (2) trả lời sớm và đúng intent, (3) giá trị riêng, (4) bằng chứng, (5) đọc và cấu trúc, (6) tích hợp thương mại, (7) giọng văn/chính tả.
5. **Sửa khi được yêu cầu:** giữ giọng tác giả, không thêm dữ kiện. Bổ sung chỉ từ nguồn người dùng cung cấp; chỗ thiếu thì để `[DATA NEEDED: ...]`/`[EXPERIENCE: ...]` kèm câu hỏi cho đúng bộ phận. Chạy lại script, nói rõ điểm trước/sau.
6. **Kết luận** một trong ba: *sẵn sàng cho biên tập người* / *cần sửa* / *viết lại phần lớn*, cùng các sự thật cần người xác minh (số liệu, tên, ngày).

## Những điều không bao giờ làm

- **Không bịa trải nghiệm, số liệu, review, "chúng tôi đã test"** để bài trông có thẩm quyền. Google đánh giá cao bằng chứng trải nghiệm thật; bịa còn rủi ro pháp lý (FTC 16 CFR 465; CMA DMCC Act).
- **Không độn chữ** để đủ độ dài (không có độ dài lý tưởng), không lặp biến thể keyword, không thêm FAQ giả.
- Không thêm CTA "buy now" để "tăng chuyển đổi"; bài hữu ích dẫn sang sản phẩm bằng ngữ cảnh (xem `product-slot`).
- Không cam kết xếp hạng. Điểm của script là heuristic nội bộ, **không phải điểm của Google**.

## Nội dung do AI hỗ trợ

Hướng dẫn của Google: AI hữu ích để nghiên cứu và dựng cấu trúc, nhưng tạo nhiều trang không thêm giá trị là scaled content abuse; mô hình có thể sai sự thật nên phải kiểm chứng; nên cân nhắc nói cách nội dung được tạo ra. Vì vậy với bản nháp AI: (a) kiểm chứng từng số liệu/tên/ngày, (b) thêm ít nhất một giá trị gốc thật, (c) biên tập người trước khi đăng, (d) không xuất bản hàng loạt không duyệt. Quality Rater Guidelines xem nội dung chính tạo bằng công cụ tự động với ít công sức/độc đáo/giá trị là mức chất lượng thấp nhất.

## Tài liệu kèm

- `references/rubric.md`: 8 chiều đánh giá, câu hỏi, thang điểm, dấu hiệu đỏ, cách sửa.
- `references/voice-and-style.md`: giọng văn cho blog quà tặng, US vs UK, plain language, thay thế cụm sáo rỗng.
