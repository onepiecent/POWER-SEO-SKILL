---
name: product-slot
description: Convention and tools for mentioning products naturally in Printerval blog posts without URLs. Writers leave a PRODUCT-SLOT placeholder that describes the product, the reader's situation and the reason, and the content team replaces it with a real link. Checks slot density, placement and quality, exports a hand-off CSV, and builds a version of the post without products to test whether it is still useful. Use when the user mentions product links, slots, natural product placement, hand-off to the content team, or posts that read like ads.
---

# Product slot

Blog nên dẫn người đọc sang trang bán hàng, nhưng **tự nhiên**. Vì URL sản phẩm/danh mục của Printerval đang thay đổi và do team content phụ trách, writer không gắn link; họ để lại **slot** mô tả đúng ngữ cảnh, và team content chọn sản phẩm/link thật phù hợp.

## Cú pháp

```
[PRODUCT-SLOT: personalized pet-portrait mug | context: gift for a dog mom | why: she sees her own dog on it every morning]
```

| Trường | Bắt buộc | Nội dung |
|---|---|---|
| (đầu tiên) | có | loại sản phẩm/ý tưởng, **không URL** |
| `context:` | có | tình huống của người đọc mà sản phẩm giải quyết |
| `why:` | có | vì sao hợp với tình huống đó (nói về người đọc, ≥ 5 từ, không khẩu hiệu bán hàng) |
| `alt:` | không | phương án thay thế nếu sản phẩm đầu không có |

## Bài kiểm tra "tự nhiên" (đọc `references/natural-integration.md`)

1. **Bỏ-hết-slot:** xóa mọi slot, bài còn đầy đủ và hữu ích không? (`slot_check.py --strip`)
2. **Vấn đề người đọc:** slot giải quyết đúng một vấn đề đang được bàn ở đoạn đó?
3. **Cụ thể:** `why` nói điều chỉ đúng với sản phẩm/ngữ cảnh này (không dùng được cho mọi sản phẩm)?
4. **Vị trí:** không nằm trong phần mở bài; không dồn cuối bài; không hai slot sát nhau.
5. **Trung thực:** không hứa giá, giao hàng, kết quả; claim kèm slot vẫn qua `claims-compliance-check`.

## Công cụ

```bash
python3 skills/product-slot/scripts/slot_check.py draft.md --post-type gift-guide
python3 skills/product-slot/scripts/slot_check.py draft.md --export slots.csv     # bàn giao team content
python3 skills/product-slot/scripts/slot_check.py draft.md --strip preview.md     # bản không slot để đọc thử
python3 skills/product-slot/scripts/slot_check.py final.md --final                # trước khi đăng: không còn slot
```

Ngưỡng tham khảo **[Quy ước]** (không phải quy tắc của Google), theo loại bài (tối đa slot/1.000 từ; số từ đầu bài không có slot): gift-guide 8/80, ideas-list 8/80, choose-guide 4/100, pillar-hub 6/100, how-to/explainer/copy-ideas 2/150, mặc định 3/120. Cảnh báo thêm: `why` quá ngắn hoặc có từ quảng cáo ("best", "perfect", "must-have"...), URL trong slot (lỗi), hơn một nửa slot ở 20% cuối bài, hai slot cách nhau < 60 từ.

## Quy trình với team content

1. Writer viết bài hữu ích trước, để slot ở chỗ sản phẩm là lời giải tự nhiên.
2. Biên tập chạy `slot_check.py` (không còn lỗi), `--export slots.csv`.
3. Team content điền cột `link_added` và `link_or_note` cho từng slot, thay slot bằng câu văn + link thật (anchor mô tả; link affiliate/sponsored nếu có dùng `rel="sponsored"`), hoặc **xóa slot** nếu không có sản phẩm phù hợp (không ép).
4. Chạy `--final` (không còn slot) và `claims_check.py`; đọc lại cả đoạn cho tự nhiên.

## Với thị trường UK

ASA có thể xem nội dung trên website của nhà bán gắn trực tiếp với việc bán hàng là quảng cáo thuộc phạm vi CAP Code; mọi claim khách quan quanh slot phải chứng minh được. Xác nhận cách công bố với pháp chế.
