# Loại pillar cho blog POD (và độ phủ kỳ vọng)

Đây là **khung tổ chức [Quy ước]**. Điểm chung: pillar phải mang giá trị riêng (giúp người đọc quyết định), không chỉ là danh sách link.

| Loại pillar (`pillar_type`) | Ví dụ | Tên gợi ý | Độ phủ kỳ vọng (khoảng trống được báo nếu thiếu) |
|---|---|---|---|
| **occasion** (dịp lễ) | mothers-day, christmas, halloween | "{Occasion} Gift Ideas" | gift guide theo người nhận/ngân sách; slogan/lời nhắn thiệp; câu hỏi thông tin (ngày, ý nghĩa) |
| **interest** (sở thích/đam mê) | dogs, fishing, gaming | "Gift Ideas for {Audience}" | gift guide; slogan/quote; how-to cá nhân hóa/thiết kế/chăm sóc |
| **recipient** (người nhận) | mom, teacher, nurse | "Gift Ideas for {Recipient}" | gift guide; slogan/lời nhắn |
| **craft** (kiến thức chuyên môn) | sizing, care, print-methods, design | "Sizing & Fit Guide", "Care & Washing Guide"... | how-to/solve; giải thích/so sánh (info/choose) |
| **inspiration** (cảm hứng chữ) | slogans, quotes, captions | "Slogans, Quotes & Caption Ideas" | theo giọng điệu/quan hệ/dịp |
| **product** (theo sản phẩm, tầng cuối) | shirts, mugs | "{Product}: Ideas & Guides" | gift guide + how-to |
| **category** (tự định nghĩa) | Pets, Work & school | tên nhóm của bạn | tùy brief |

## Vì sao có pillar "craft" và "inspiration"

- **craft** là nơi Printerval có kinh nghiệm thật (in ấn, chất liệu, size, chăm sóc, cá nhân hóa). Google ưu tiên nội dung có góc nhìn và kinh nghiệm trực tiếp ("non-commodity"); đây là loại bài khó bị thay thế bằng tóm tắt chung chung. Mọi khẳng định riêng về sản phẩm của Printerval phải đến từ tài liệu của team sản phẩm.
- **inspiration** (slogan, quote, caption, lời nhắn thiệp) hữu ích độc lập với việc mua hàng và dẫn tới sản phẩm tùy chỉnh rất tự nhiên (người đọc cần chữ để đặt lên áo/cốc). Dùng nội dung gốc, không sao chép lời bài hát, câu thoại phim, khẩu hiệu thương hiệu.

## Trang hub (bài pillar) tốt

- Màn hình đầu giúp người chỉ đọc 30 giây: "Nếu bạn cần X, đọc Y".
- Mỗi cluster có 2-3 câu tóm tắt kèm một link ngữ cảnh; không lặp nội dung cluster.
- Pillar theo mùa **giữ nguyên một URL và làm mới hằng năm**; chỉ đổi ngày hiển thị khi nội dung thật sự đổi (Google: không làm mới ngày giả).
- Pillar quá 30 cụm: tách thành hub con (ví dụ theo người nhận) thay vì một trang dài vô tận.

## Liên kết chéo giữa pillar

Cụm có facet thứ hai trùng pillar khác (ví dụ "Mother's Day gift ideas for dog moms" thuộc pillar Mother's Day nhưng có `interest=dogs`) được `internal-link-planner` đề xuất link chéo sang pillar sở thích (loại `cross_pillar`). Giữ tối đa 1 link chéo mỗi bài để không loãng.
