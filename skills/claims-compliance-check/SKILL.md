---
name: claims-compliance-check
description: Flags risky claims in US and UK Printerval blog posts under FTC, CMA and ASA guidance (delivery times and order deadlines, reviews and popularity, environmental, health, price and offer claims, made in USA or handmade, absolute comparisons, we-tested experience claims, affiliate and sponsorship disclosure) and flags brand and IP names (franchises, artists) in a draft or a keyword list. Use when the user mentions claims, legal checks, FTC, CMA, ASA, fake reviews, delivery promises, eco-friendly wording, trademarks, IP or affiliate disclosure before publishing. Not legal advice.
---

# Claims & compliance check

Công cụ **gắn cờ** để người/pháp chế quyết định; không kết luận hợp pháp hay vi phạm và **không phải tư vấn pháp lý**. Rủi ro cao (sức khỏe, môi trường, giao hàng, review, nhãn hiệu) nên được pháp chế hoặc bộ phận liên quan xác nhận.

## Chạy

```bash
python3 skills/claims-compliance-check/scripts/claims_check.py draft.md --market us
python3 skills/claims-compliance-check/scripts/claims_check.py draft.md --market uk --json report.json
python3 skills/claims-compliance-check/scripts/claims_check.py --keywords outputs/keyword-map.csv --column keyword   # cổng IP trước khi lên brief
```

Mã thoát = 1 nếu còn phát hiện mức `high` chưa xử lý (dùng như cổng trước khi đăng).

## Các quy tắc và cơ sở

| Rule | Mức | Cơ sở (xem `references/us-uk-claims.md`) |
|---|---|---|
| `delivery_promise` | high | FTC Mail/Internet Order Merchandise Rule: cơ sở hợp lý cho thời gian giao hàng; CMA/ASA: chứng minh được |
| `review_testimonial` | high | FTC 16 CFR Part 465 (hiệu lực 21/10/2024); CMA DMCC Act (từ 4/2025, CMA208) |
| `eco_general` | high | FTC Green Guides; CMA Green Claims Code |
| `health_claim` | high | FTC Act s.5; ASA/CAP Code |
| `made_in` | high | FTC chuẩn "Made in USA" |
| `ip_brand` | high | USPTO/UK IPO: nguy cơ nhầm lẫn nhãn hiệu; quyền nhân thân với tên nghệ sĩ |
| `eco_specific`, `superlative_guarantee`, `price_offer`, `policy_claim`, `first_hand_claim`, `disclosure` | medium | FTC/CMA/ASA; Google (bằng chứng trải nghiệm) |
| `handmade_claim` | low | CMA/ASA/FTC (bỏ qua nếu chỉ là chủ đề DIY) |
| `uk_remit_note` | info | ASA: nội dung trên website của nhà bán gắn trực tiếp với việc bán hàng có thể thuộc phạm vi CAP |

Mỗi phát hiện in: dòng, đoạn trích, các cụm khớp, nguồn, lý do, **cách xử lý** đề xuất.

## Cách xử lý phát hiện

1. **Sửa hoặc bỏ** claim nếu không có bằng chứng. Với giao hàng, giá, review: thay bằng `[DATA NEEDED: ... do bộ phận X xác nhận, ngày]` hoặc bỏ.
2. **Có bằng chứng:** đưa nguồn vào bài (link/ngày) và, nếu cần, nhờ người có thẩm quyền duyệt rồi để dấu miễn trừ ngay trong đoạn: `[CLAIM-OK: lý do; người duyệt; ngày]`. Đoạn có dấu này được liệt kê trong mục "đã miễn trừ" thay vì báo lỗi; **không tự đặt dấu này** thay cho người duyệt.
3. **Trải nghiệm trực tiếp:** giữ "we tested/our team..." chỉ khi đoạn có `[EXPERIENCE: nguồn]` hoặc `[DATA: nguồn]` thật; không bịa.
4. **IP:** hỏi pháp chế; nhắc tên với mục đích thông tin trung thực khác với dùng tên đó để bán/quảng bá sản phẩm mang nhãn. Tránh đưa tên vào tiêu đề, H2, anchor và mô tả sản phẩm khi chưa được duyệt.

## Danh sách IP

`assets/ip-watchlist.txt` chỉ là **danh sách khởi đầu, không đầy đủ**; team pháp chế/IP của Printerval cần duy trì danh sách thật (một tên mỗi dòng; `re:` cho regex). Dùng chế độ `--keywords` ngay sau bước gom nhóm để loại/duyệt keyword có nhãn hiệu trước khi viết brief.

## Giới hạn

- Regex bắt dấu hiệu bề mặt: có thể báo thừa (ví dụ "treat stains" không bị bắt, nhưng "sustainable fashion" trong bài bình luận có thể bị bắt) và bỏ sót cách diễn đạt khác. Luôn đọc ngữ cảnh.
- Quy định thay đổi và có ngoại lệ theo bang/ngành; xem `references/us-uk-claims.md` để biết mức xác minh từng nguồn.
