#!/usr/bin/env python3
"""Kiểm tra và xuất các [PRODUCT-SLOT] trong bài blog. Chỉ dùng thư viện chuẩn.

Quy ước slot (writer để lại, team content thay bằng link thật):
    [PRODUCT-SLOT: personalized pet-portrait mug | context: gift for a dog mom | why: she sees her own dog on it]
  - trường đầu: loại sản phẩm / ý tưởng (KHÔNG URL)
  - context: tình huống của người đọc mà sản phẩm giải quyết
  - why: vì sao sản phẩm hợp với tình huống đó (nói về người đọc, không phải khẩu hiệu bán hàng)
  - alt (tùy chọn): phương án thay thế

Chạy:
    slot_check.py draft.md --post-type gift-guide
    slot_check.py draft.md --export slots.csv        # bàn giao cho team content
    slot_check.py draft.md --strip preview.md        # đọc bài khi KHÔNG có sản phẩm: có còn hữu ích không?
    slot_check.py final.md --final                   # trước khi đăng: không được còn slot nào

Ngưỡng là QUY ƯỚC biên tập (mục tiêu: nhắc sản phẩm tự nhiên, bài vẫn hữu ích khi bỏ hết slot), không phải quy tắc của Google.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys

SLOT_RX = re.compile(r"\[PRODUCT-SLOT:(.*?)\]", re.S)
HEADING_RX = re.compile(r"^#{1,6}\s+(.+)$", re.M)
URL_RX = re.compile(r"https?://|www\.|\.com\b|\.co\.uk\b", re.I)
PROMO_RX = re.compile(r"\b(best|#1|number one|perfect|must[- ]have|amazing|guaranteed|unbeatable|bestseller|"
                      r"best[- ]selling|top[- ]rated|incredible|life[- ]changing)\b", re.I)
REQUIRED = ("context", "why")
# (tối đa slot / 1.000 từ, số từ đầu bài không được có slot)
LIMITS = {"gift-guide": (8, 80), "ideas-list": (8, 80), "choose-guide": (4, 100), "pillar-hub": (6, 100),
          "how-to": (2, 150), "explainer": (2, 150), "copy-ideas": (2, 150), "generic": (3, 120)}


def parse_slot(raw: str) -> dict:
    parts = [p.strip() for p in raw.split("|")]
    out = {"product": parts[0] if parts else "", "context": "", "why": "", "alt": ""}
    for p in parts[1:]:
        key, _, val = p.partition(":")
        key = key.strip().lower()
        if key in ("context", "why", "alt"):
            out[key] = val.strip()
        elif p:
            out.setdefault("extra", []).append(p)
    return out


def words_in(text: str) -> int:
    return len(SLOT_RX.sub(" ", text).split())


def analyse(text: str, post_type: str):
    max_per_1000, intro_words = LIMITS.get(post_type, LIMITS["generic"])
    total = max(1, words_in(text))
    slots = []
    for i, m in enumerate(SLOT_RX.finditer(text), 1):
        before = text[:m.start()]
        headings = HEADING_RX.findall(before)
        s = parse_slot(m.group(1))
        s.update({"id": f"S{i:02d}", "words_before": words_in(before), "section": headings[-1].strip() if headings else "",
                  "line": before.count("\n") + 1,
                  "context_text": re.sub(r"\s+", " ", SLOT_RX.sub("", text[max(0, m.start() - 100):m.end() + 100])).strip()})
        slots.append(s)
    issues: list[tuple[str, str, str]] = []  # (severity, slot, message)
    for s in slots:
        for f in REQUIRED:
            if not s[f]:
                issues.append(("error", s["id"], f"thiếu trường '{f}:'"))
        if URL_RX.search(s["product"] + s["context"] + s["why"] + s["alt"]):
            issues.append(("error", s["id"], "có URL trong slot: team content gắn link, writer không gắn"))
        if s["why"] and len(s["why"].split()) < 5:
            issues.append(("warn", s["id"], "'why' quá ngắn; giải thích vì sao hợp với tình huống của người đọc"))
        if PROMO_RX.search(s["why"] + " " + s["product"]):
            issues.append(("warn", s["id"], "ngôn ngữ quảng cáo/so sánh tuyệt đối trong slot; mô tả lợi ích cho người đọc thay vì khẩu hiệu"))
        if s["words_before"] < intro_words:
            issues.append(("warn", s["id"], f"slot nằm trong {intro_words} từ đầu bài: trả lời người đọc trước, sản phẩm sau"))
    density = len(slots) / total * 1000
    if density > max_per_1000:
        issues.append(("warn", "-", f"mật độ {density:.1f} slot/1.000 từ vượt mức tham khảo {max_per_1000} cho '{post_type}'"))
    if len(slots) >= 3:
        tail = sum(1 for s in slots if s["words_before"] > 0.8 * total)
        if tail / len(slots) > 0.5:
            issues.append(("warn", "-", "hơn một nửa slot dồn ở 20% cuối bài: trông như quảng cáo gắn thêm"))
    for a, b in zip(slots, slots[1:]):
        if b["words_before"] - a["words_before"] < 60:
            issues.append(("warn", f"{a['id']}/{b['id']}", "hai slot cách nhau dưới 60 từ: dồn sản phẩm"))
    return slots, issues, total, density


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--post-type", default="generic", choices=sorted(LIMITS))
    ap.add_argument("--export", help="ghi CSV bàn giao cho team content")
    ap.add_argument("--strip", help="ghi bản bài đã bỏ hết slot để kiểm tra bài còn tự đứng được không")
    ap.add_argument("--final", action="store_true", help="trước khi đăng: còn slot nào thì FAIL")
    args = ap.parse_args(argv)

    with open(args.file, encoding="utf-8") as fh:
        text = fh.read()
    slots, issues, total, density = analyse(text, args.post_type)
    print(f"{len(slots)} slot / {total:,} từ ({density:.1f} slot/1.000 từ), loại bài: {args.post_type}")
    for sev, sid, msg in sorted(issues, key=lambda i: (i[0] != "error", i[1])):
        print(f"  [{sev}] {sid}: {msg}")
    if args.final and slots:
        print(f"  [error] --final: còn {len(slots)} slot chưa được thay bằng link/nội dung thật")
        issues.append(("error", "-", "slot còn lại khi --final"))
    if args.export:
        with open(args.export, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["slot_id", "section", "product_idea", "reader_context", "why_it_helps", "alternative",
                        "approx_word_position", "line", "surrounding_text", "link_added(Y/N)", "link_or_note"])
            for s in slots:
                w.writerow([s["id"], s["section"], s["product"], s["context"], s["why"], s["alt"], s["words_before"],
                            s["line"], s["context_text"], "", ""])
        print(f"Đã xuất {len(slots)} slot -> {args.export}")
    if args.strip:
        clean = re.sub(r"[ \t]{2,}", " ", SLOT_RX.sub("", text))
        clean = re.sub(r"[ \t]+([.,;:!?])", r"\1", clean)
        with open(args.strip, "w", encoding="utf-8") as fh:
            fh.write(clean)
        print(f"Đã ghi bản không slot -> {args.strip} (đọc lại: bài còn đầy đủ và hữu ích không?)")
    return 1 if any(i[0] == "error" for i in issues) else 0


if __name__ == "__main__":
    sys.exit(main())
