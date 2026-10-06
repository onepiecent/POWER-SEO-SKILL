# Giọng văn và phong cách (blog quà tặng, US/UK)

Chi tiết ngữ pháp, chính tả và công cụ kiểm tra nằm ở skill **english-grammar-style**; đây là phần riêng cho blog Printerval.

## Giọng

- Ấm, cụ thể, thực tế: nói như một người biết cách chọn quà và cách cá nhân hóa đồ in, không như quảng cáo.
- Cụ thể thắng hoa mỹ: "a photo with faces filling most of the frame prints more clearly" thay vì "stunning, high-quality prints".
- Nói thẳng nhược điểm và giới hạn ("personalized items usually cannot be returned if the name is misspelled" **chỉ khi đúng chính sách thật**).
- Dịp nhạy cảm (tang, mất người thân, không có con/cha mẹ): đừng giả định hoàn cảnh; đưa lựa chọn nhẹ nhàng.
- Không phán xét người nhận, không rập khuôn giới/tuổi; dùng ngôn ngữ bao gồm.

## US vs UK

| | US | UK |
|---|---|---|
| Chính tả | color, personalized, favorite, center, gray | colour, personalised, favourite, centre, grey |
| Từ vựng | mom, sneakers, sweater, vacation, bachelorette | mum, trainers, jumper, holiday, hen do |
| Tiền tệ, ngày | $; "May 9, 2027" | £; "9 May 2027" hoặc "Sunday 9 May" |
| Đơn vị | °F, inches, lb | °C, cm, kg (dặm cho đường bộ) |
| Giọng | trực tiếp, nhiệt tình chấp nhận được | tiết chế hơn, ít cường điệu ("amazing", "incredible" dày đặc nghe giả) |

Chọn **một** biến thể cho cả bài (`helpful_check.py --market` báo trộn lẫn). Anchor và title cũng theo biến thể.

## Plain language (cơ sở của ngưỡng độ đọc)

Hướng dẫn plain language của chính phủ Mỹ (plainlanguage.gov) và GOV.UK style guide cùng khuyến nghị: câu ngắn, từ đơn giản, chủ động, ví dụ cụ thể, tiêu đề phụ rõ. Mục tiêu tham khảo **[Quy ước]**: Flesch-Kincaid ≤ ~9-10, câu trung bình 15-20 từ, đoạn 2-4 câu. Thuật ngữ in ấn (DTG, sublimation, GSM) phải giải thích ở lần đầu.

## Thay thế cụm sáo rỗng/giọng AI

| Thay vì | Viết |
|---|---|
| In today's fast-paced world, finding the perfect gift... | Finding a gift your grandma will use takes more than a quick search. |
| Look no further! / Unlock the power of gifting | (bỏ; đi thẳng vào gợi ý đầu tiên) |
| It's important to note that... | (bỏ; nói luôn điều quan trọng) |
| Whether you're shopping for X or Y... | Name the person: "If she reads every evening, ..." |
| Delve into / dive into / navigate the world of | cover / look at / explain |
| a rich tapestry of / seamless / robust / leverage | (dùng từ cụ thể: "a wide range of", "easy", "reliable", "use") |
| In conclusion, | (kết ngắn, có hành động tiếp theo hữu ích) |
| The ultimate / perfect gift for everyone | "A good fit if she ..., less so if ..." |

Script `helpful_check.py` đếm các cụm này; đừng sửa máy móc, đọc lại câu cho tự nhiên.

## Tiêu đề, ảnh, định dạng

- H1 một lần; H2 theo câu hỏi/nhu cầu của người đọc; không lặp nguyên cụm từ khóa ở mọi H2.
- ALT mô tả ảnh (ảnh trang trí để `alt=""`); tên file chữ thường, gạch nối (xem skill `seo-content-vn`).
- Bảng khi so sánh, danh sách đánh số khi có quy trình, danh sách gạch khi liệt kê ngang hàng.
- Hiển thị tác giả, ngày đăng và "Last updated" thật.
