# Nhu cầu người đọc (`reader_need`) và độ phù hợp với blog (`blog_fit`)

Mỗi keyword được gán đúng một nhu cầu bằng quy tắc regex (thứ tự ưu tiên từ trên xuống; quy tắc nằm trong `assets/taxonomy.json` -> `reader_need_rules`). Đây là **heuristic [Quy ước]**: xác nhận lại bằng SERP thật cho các cụm quan trọng.

| `reader_need` | Dấu hiệu | Ví dụ | `blog_fit` | Loại bài thường gặp |
|---|---|---|---|---|
| `shop` | buy, order, cheap, discount, coupon, price, wholesale, near me; hoặc chỉ có tên sản phẩm (kèm phong cách) | "custom mugs", "buy personalized mug" | **low** | Bỏ khỏi bản đồ blog: trang bán hàng/team content xử lý |
| `how_to` | how to, DIY, steps to, ways to, tutorial | "how to wash a graphic tee" | high | how-to |
| `copy_ideas` | slogans, quotes, captions, sayings, taglines, what to write, name ideas | "funny t shirt slogans", "mother's day quotes" | high | copy-ideas |
| `choose` | best, vs, which, review, compare, worth it, buying guide | "dtg vs screen printing", "best gifts for nurses" | high | choose-guide hoặc gift-guide |
| `solve` | fix, remove, shrink, fade, wash, care, size, fit, stain | "t-shirt size chart men" | high | how-to |
| `inspire` | ideas, gifts, presents, what to get | "gifts for dog lovers", "mother's day gift ideas" | high | gift-guide, ideas-list, pillar-hub |
| `info` | what/why/when/where/who..., meaning, history, date | "when is mother's day", "what is dtg printing" | medium | explainer (thường chỉ là một mục trong bài pillar) |

## Gom cụm theo nhu cầu

`inspire` và `choose` được xem là cùng nhóm "list" (người đọc muốn một danh sách có lý do chọn): "best gifts for nurses" và "gifts for nurses" có thể vào cùng một cụm. Các loại còn lại phải trùng nhau mới gộp ("how to wash" không gộp với "what is DTG").

## Khi nào nên nghi ngờ nhãn

- Từ khóa chỉ là tên sản phẩm kèm tính từ ("funny dad shirts") bị gán `shop`; nếu SERP toàn bài hướng dẫn/ý tưởng thì đổi thủ công thành bài blog.
- Câu hỏi về chính sách ("how long does shipping take") thuộc `info` nhưng là nội dung dịch vụ: cần dữ liệu vận hành, không tự viết (xem `claims-compliance-check`).
- Nhu cầu `info` có volume theo mùa rất lớn ("when is mother's day") nhưng cạnh tranh với kết quả trực tiếp của Google; thường nên là một mục ngắn trong bài pillar.
