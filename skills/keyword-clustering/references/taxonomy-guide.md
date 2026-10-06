# Mở rộng taxonomy, nhóm tự định nghĩa và quy tắc nhiễu

Ba cấu hình có thể chỉnh mà không sửa code:

| Mục đích | File | Dùng |
|---|---|---|
| Thêm niche/dịp/người nhận/sản phẩm mới cho facet | JSON mở rộng | `--extend-taxonomy file.json` (hoặc sửa thẳng `assets/taxonomy.json`) |
| Nhóm theo cách riêng của brief (Family, Pets, Work...) | `categories.json` | `--categories categories.json --group-by category` |
| Thêm/bớt quy tắc loại nhiễu | `assets/noise-rules.json` | `--noise-rules file.json` hoặc `--no-noise-filter` |

## 1. Mở rộng taxonomy

Cấu trúc: `facets -> <facet> -> values -> <key> -> {label, patterns, seasonal?}`. Facet: `occasion`, `interest`, `recipient`, `product`, `style`, `craft`.

```json
{
  "facets": {
    "interest": {"values": {"pickleball": {"label": "Pickleball Players", "patterns": ["\\bpickleball\\w*\\b"]}}},
    "recipient": {"values": {"nurse": {"patterns": ["\\bnurse practitioners?\\b"]}}}
  }
}
```

- **Key mới** được thêm; **key đã có** thì pattern được nối thêm (và các trường khác như label được ghi đè).
- Pattern là **regex Python chạy trên văn bản đã chuẩn hóa**: chữ thường, bỏ dấu nháy (`mother's` -> `mothers`), gạch nối -> khoảng trắng (`t-shirt` -> `t shirt`). Luôn dùng biên từ `\b` và nhớ dạng số nhiều/biến thể (`fisherm[ae]n`, `anglers?`).
- `label` dùng để đặt tên pillar ("Gift Ideas for Pickleball Players"). Người nhận có biến thể UK thì thêm `label_uk` (vd Mum, Nan & Grandma).
- `"seasonal": true` cho dịp lễ có ngày cụ thể; sau đó thêm quy tắc ngày vào `editorial-calendar/scripts/occasion_calendar.py` (OCCASIONS), nếu không `seasonal-plan.csv` sẽ báo `no_calendar_rule`.
- Ngoài facet còn có thể thêm `weak_tokens`, `variants` (UK->US cho so khớp), `phrase_variants`, `us_only_terms`, `uk_only_terms`, `blog_fit`, và `reader_need_rules_prepend` (quy tắc nhu cầu đặt lên đầu).

**Quy trình đề xuất khi file có nhiều keyword chưa phân loại:** mở `taxonomy-suggestions.csv` (n-gram phổ biến trong keyword chưa nhận diện, sắp theo volume), nhóm các gợi ý có nghĩa thành niche/dịp, viết JSON mở rộng, chạy lại và so sánh tỷ lệ chưa phân loại. Với mỗi niche mới, kiểm tra trên một mẫu keyword thật rằng regex không khớp nhầm (ví dụ "bird" trong "bird watching" nhưng không phải "birdie" của golf).

**Thứ tự dò và "che":** dịp lễ rồi sở thích được dò trước, và đoạn đã khớp bị che đi để facet sau không đếm lại ("dog mom" -> `interest=dogs`, `recipient=mom`; "mother's day" không làm `recipient=mom`). "Gifts from daughter" không tính daughter là người nhận.

## 2. `categories.json` (nhóm tự định nghĩa)

```json
{
  "Pets": ["dog", "cat", "puppy", "kitten", "pet"],
  "Family & relationships": ["mom", "dad", "grandma", "family"],
  "Work & school": ["teacher", "nurse", "re:\\bback to school\\b"]
}
```

- Mỗi từ tự thêm biên từ và số nhiều (`dog` khớp `dogs`); tiền tố `re:` dùng regex thô.
- Keyword gán vào nhóm **khớp đầu tiên theo thứ tự trong file**; không khớp = `(none)`. Đặt nhóm cụ thể lên trước nhóm rộng.
- `--group-by category` cần file này. Có thể kết hợp: `--group-by category,occasion`.
- `topic-map` hiểu `category` như một facet: `topic_map.py clusters.csv --priority category,occasion`.

## 3. Quy tắc loại nhiễu

`assets/noise-rules.json`: danh sách `rules`, mỗi rule có `name` (hiện trong `excluded.csv`), `on` (`norm` hoặc `raw`) và `patterns`. Mặc định: retailer/brand điều hướng (kể cả đối thủ POD và retailer UK), tài khoản/hỗ trợ/uy tín thương hiệu (login, scam, legit...), ý định local (near me), gift-card balance, nội dung người lớn, tiếng Tây Ban Nha, URL/domain; cộng giới hạn độ dài (12 từ/120 ký tự) và tỷ lệ ký tự không phải Latin.

Nguyên tắc chỉnh: mỗi rule chỉ nên loại thứ **chắc chắn không thuộc blog**; những gì chỉ "ít phù hợp" thì để `blog_fit` xử lý. Sau khi sửa rule, đọc lại `excluded.csv` sắp theo volume để chắc chắn không loại nhầm keyword lớn.
