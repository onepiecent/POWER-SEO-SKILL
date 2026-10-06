#!/usr/bin/env python3
"""Soát claim rủi ro pháp lý/quảng cáo trong bài blog US/UK, và gắn cờ IP trong danh sách keyword.
Chỉ dùng thư viện chuẩn. KHÔNG phải tư vấn pháp lý: công cụ chỉ gắn cờ để người/pháp chế quyết định.

Chạy:
    claims_check.py draft.md --market us
    claims_check.py draft.md --market uk --json report.json
    claims_check.py --keywords keyword-map.csv --column keyword      # cổng IP trước khi lên brief

Đã soát và được người có thẩm quyền duyệt thì để ngay trong đoạn: [CLAIM-OK: lý do; người duyệt; ngày]
(đoạn đó được bỏ qua và liệt kê trong mục "đã miễn trừ").
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WATCHLIST = os.path.join(HERE, "..", "assets", "ip-watchlist.txt")

FTC_REVIEWS = "FTC 16 CFR Part 465 (review giả/testimonial, hiệu lực 21/10/2024)"
CMA_REVIEWS = "CMA DMCC Act 2024: review giả/khuyến khích không công bố bị cấm từ 4/2025 (CMA208)"
FTC_SHIP = "FTC Mail, Internet, or Telephone Order Merchandise Rule: phải có cơ sở hợp lý cho thời gian giao hàng"
FTC_GREEN = "FTC Green Guides (16 CFR 260); CMA Green Claims Code"
ASA_CAP = "ASA/CAP Code: claim khách quan phải chứng minh được; nội dung trên website của nhà bán gắn trực tiếp với việc bán hàng có thể thuộc phạm vi CAP"

# id, mức, regex (trên văn bản gốc, không phân biệt hoa thường), thị trường áp dụng, nguồn, thông điệp, cách sửa
RULES = [
    ("delivery_promise", "high",
     r"\b(arrives? by|delivered? (by|in|within)|ships? (in|within|by)|fast (shipping|delivery)|next[- ]day|same[- ]day|"
     r"guaranteed delivery|order by|last order date|cut-?off|overnight (shipping|delivery)|express (shipping|delivery)|"
     r"before (christmas|mother'?s day|mothering sunday|father'?s day|valentine'?s( day)?|halloween|easter))\b",
     ("us", "uk"), FTC_SHIP + "; " + ASA_CAP,
     "Lời hứa thời gian giao hàng/hạn đặt hàng cần dữ liệu vận hành đã xác nhận và điều kiện đi kèm.",
     "Thay bằng [DATA NEEDED: hạn đặt hàng do bộ phận vận hành xác nhận, ngày xác nhận] hoặc bỏ."),
    ("review_testimonial", "high",
     r"\b(customers? (love|say|rave|report)|\d(\.\d)?[- ]star|five[- ]star|reviews? (say|show)|rated \d(\.\d)?|"
     r"thousands of (happy )?customers|loved by|trusted by|best[- ]?sellers?|most popular|top[- ]selling|selling fast|hot seller)\b",
     ("us", "uk"), FTC_REVIEWS + "; " + CMA_REVIEWS,
     "Review/độ phổ biến phải dựa trên dữ liệu thật còn hiệu lực. Review giả (kể cả do AI tạo) và review nội bộ không công bố quan hệ đều bị cấm.",
     "Chỉ giữ nếu trích đúng số liệu thật kèm nguồn và thời điểm; nếu không, bỏ. Gắn [DATA NEEDED: nguồn review, ngày]."),
    ("eco_general", "high",
     r"\b(eco[- ]?friendly|sustainabl[ey]|environmentally friendly|planet[- ]friendly|climate[- ]friendly|"
     r"carbon[- ]neutral|net[- ]zero|zero waste|go green|green (product|choice|alternative|living|credentials))\b",
     ("us", "uk"), FTC_GREEN,
     "Claim môi trường chung chung (eco-friendly, sustainable...) rất khó chứng minh; Green Guides khuyên không dùng không kèm giới hạn cụ thể.",
     "Nêu thuộc tính cụ thể, đo được và có bằng chứng (vd tỷ lệ vật liệu tái chế đã xác minh) hoặc bỏ."),
    ("eco_specific", "medium",
     r"\b(recycled|recyclable|biodegradable|compostable|organic|vegan|cruelty[- ]free|non[- ]toxic|ethically (made|sourced))\b",
     ("us", "uk"), FTC_GREEN,
     "Claim vật liệu/môi trường cụ thể cần chứng nhận hoặc tài liệu nhà cung cấp.",
     "Ghi rõ chứng nhận/nguồn (vd tên chứng nhận, tỷ lệ) với [DATA NEEDED: tài liệu nhà cung cấp] hoặc bỏ."),
    ("health_claim", "high",
     r"\b(cures?|clinically (proven|tested)|doctor[- ]recommended|medically (proven|tested|approved)|"
     r"anti[- ]?(bacterial|microbial|viral)|therapeutic|heals?|(reduces?|relieves?) (stress|anxiety|pain|symptoms))\b",
     ("us", "uk"), ASA_CAP + "; FTC Act s.5 (claim sức khỏe cần bằng chứng khoa học)",
     "Claim sức khỏe/y tế đối với sản phẩm cần bằng chứng khoa học đủ mạnh.",
     "Bỏ, hoặc chỉ nói về trải nghiệm cảm xúc của món quà thay vì tác dụng y tế."),
    ("superlative_guarantee", "medium",
     r"(\b(our|we|printerval)\b[^.\n]{0,40}\bbest\b|\bbest (price|quality|seller|selling|deal|value|in the (world|business|industry))\b|"
     r"(?<![\w])#1(?![\w])|\bnumber one\b|\bguarantee[sd]?\b|\bunbeatable\b|\brisk[- ]free\b|"
     r"\b100% (satisfaction|safe|natural|organic|cotton)\b|\blowest price\b|\bprice match\b)",
     ("us", "uk"), ASA_CAP + "; FTC Act s.5",
     "Claim so sánh tuyệt đối/bảo đảm là claim khách quan: cần bằng chứng hoặc điều kiện rõ ràng.",
     "Viết là lựa chọn của biên tập kèm tiêu chí ('our pick for ... because ...'), hoặc dẫn bằng chứng."),
    ("price_offer", "medium",
     r"(\b\d+\s?% off\b|\bfree shipping\b|\bfree returns?\b|\bon sale\b|\bdiscount(ed)?\b|\bcoupon\b|\bpromo code\b|"
     r"\b(save|from|only|just) [$£]\s?\d)",
     ("us", "uk"), "FTC Act s.5; CMA/ASA: tuyên bố giá và ưu đãi phải chính xác, còn hiệu lực",
     "Giá/ưu đãi thay đổi và phải do team thương mại xác nhận; không cố định trong bài evergreen.",
     "Bỏ giá cụ thể hoặc ghi 'as of <ngày>' với [DATA NEEDED: giá do team thương mại xác nhận]."),
    ("policy_claim", "medium",
     r"\b(money[- ]back|\d+[- ]day (returns?|guarantee|refund)|lifetime warranty|satisfaction guarantee)\b",
     ("us", "uk"), "FTC/CMA: claim chính sách phải khớp chính sách thật",
     "Claim chính sách đổi trả/bảo hành phải khớp đúng chính sách hiện hành.",
     "Trích đúng chính sách từ trang chính sách và link tới đó, hoặc bỏ."),
    ("made_in", "high",
     r"\bmade in (the )?(usa|u\.s\.a\.?|america|united states|uk|britain)\b",
     ("us", "uk"), "FTC chuẩn 'Made in USA' (gần như toàn bộ sản phẩm sản xuất tại Mỹ); CMA/ASA cho claim xuất xứ",
     "Claim xuất xứ cần đúng sự thật (sản phẩm POD thường sản xuất theo đơn bởi nhiều nhà máy ở nhiều nước).",
     "Chỉ giữ khi chuỗi cung ứng xác nhận cho đúng sản phẩm được nhắc."),
    ("handmade_claim", "low",
     r"\b(handmade|hand[- ]made|handcrafted|artisan[- ]made)\b",
     ("us", "uk"), "CMA/ASA/FTC: claim thủ công phải đúng sự thật",
     "Nếu nói về sản phẩm CỦA Printerval thì 'handmade' có thể không đúng với in theo đơn; bỏ qua nếu chỉ là chủ đề DIY.",
     "Xác nhận với vận hành hoặc dùng cách diễn đạt chính xác (vd 'made to order')."),
    ("first_hand_claim", "medium",
     r"\b(we|our team|i)\s+(tested|tried|measured|compared|reviewed|interviewed|surveyed|washed|wore)\b|\bin our (tests?|experience|lab)\b",
     ("us", "uk"), "Google (hướng dẫn viết review: có bằng chứng trải nghiệm); " + FTC_REVIEWS.split(" (")[0] + " (không dựng trải nghiệm giả)",
     "Khẳng định trải nghiệm trực tiếp phải có thật và có bằng chứng.",
     "Gắn [EXPERIENCE: nguồn nội bộ thật] trong cùng đoạn, hoặc viết lại không nhận là trải nghiệm trực tiếp."),
    ("disclosure", "medium",
     r"\b(affiliate|sponsored|paid partnership|in partnership with|gifted|sent (to us )?for free|we may earn)\b",
     ("us", "uk"), "FTC Endorsement Guides; ASA/CAP: mối quan hệ vật chất phải được công bố rõ ràng, gần nội dung",
     "Nội dung có quan hệ thương mại/được tài trợ cần công bố rõ ở đầu bài và gần chỗ liên quan.",
     "Thêm dòng công bố ở đầu bài (vd 'This post contains affiliate links...') đúng thực tế."),
]
BUDGET_RX = re.compile(r"\b(under|below|less than|up to|within|from)\s+[$£]\s?\d+", re.I)


# --------------------------------------------------------------------------- IP watchlist
def normalize(s: str) -> str:
    s = s.lower().replace("’", "'")
    s = re.sub(r"'s\b", "s", s).replace("'", "")
    s = re.sub(r"[-_/]", " ", s)
    s = re.sub(r"[^\w\s&.]", " ", s)
    return re.sub(r"\s+", " ", s.replace("&", " and ")).strip()


def load_watchlist(path: str) -> list[tuple[str, re.Pattern]]:
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("re:"):
                out.append((line, re.compile(line[3:], re.I)))
            else:
                out.append((line, re.compile(r"\b" + re.escape(normalize(line)) + r"s?\b")))
    return out


def ip_hits(text: str, watch: list) -> list[str]:
    norm = normalize(text)
    return [name for name, rx in watch if rx.search(norm)]


# --------------------------------------------------------------------------- scanning
def scan(text: str, market: str, watch: list) -> tuple[list[dict], list[dict]]:
    findings, waived = [], []
    offset = 0
    for para in re.split(r"\n\s*\n", text):
        start = text.find(para, offset)
        offset = start + len(para)
        line0 = text[:start].count("\n") + 1
        ok = re.search(r"\[CLAIM-OK:([^\]]*)\]", para)
        has_exp = bool(re.search(r"\[(EXPERIENCE|DATA):", para))
        for rid, sev, rx, markets, src, msg, fix in RULES:
            if market != "both" and market not in markets:
                continue
            if rid == "first_hand_claim" and has_exp:
                continue
            hits = []
            for m in re.finditer(rx, para, re.I):
                if rid == "price_offer" and BUDGET_RX.search(para[max(0, m.start() - 25):m.end() + 5]):
                    continue
                hits.append(m)
            if not hits:
                continue
            first = hits[0]
            item = {"rule": rid, "severity": sev, "line": line0 + para[:first.start()].count("\n"),
                    "text": para[max(0, first.start() - 40):first.end() + 40].replace("\n", " ").strip(),
                    "matched": sorted({h.group(0).lower() for h in hits}), "source": src, "message": msg, "fix": fix}
            (waived if ok else findings).append({**item, **({"waiver": ok.group(1).strip()} if ok else {})})
        for name in ip_hits(re.sub(r"\[[^\]]*\]", " ", para), watch):
            item = {"rule": "ip_brand", "severity": "high", "line": line0, "text": name, "source":
                    "USPTO/UK IPO: nguy cơ nhầm lẫn nhãn hiệu; quyền nhân thân với tên nghệ sĩ",
                    "message": "Tên thương hiệu/franchise/nghệ sĩ có thể được bảo hộ. Nhắc tới để đưa thông tin trung thực khác với "
                               "dùng tên đó để bán/quảng bá sản phẩm mang nhãn.",
                    "fix": "Hỏi pháp chế/IP: giữ ở mức nhắc thông tin, hoặc bỏ khỏi tiêu đề/H2/anchor và khỏi mô tả sản phẩm."}
            (waived if ok else findings).append({**item, **({"waiver": ok.group(1).strip()} if ok else {})})
    if market in ("uk", "both") and "[PRODUCT-SLOT:" in text:
        findings.append({"rule": "uk_remit_note", "severity": "info", "line": 0, "text": "[PRODUCT-SLOT]",
                         "source": ASA_CAP, "message": "Bài UK có nhắc sản phẩm của chính nhà bán: ASA có thể xem nội dung "
                         "gắn trực tiếp với việc bán hàng là quảng cáo thuộc phạm vi CAP.",
                         "fix": "Mọi claim khách quan trong bài phải chứng minh được; xác nhận với pháp chế về cách công bố."})
    return findings, waived


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?", help="bài viết .md/.txt cần soát")
    ap.add_argument("--market", choices=["us", "uk", "both"], default="both")
    ap.add_argument("--watchlist", default=DEFAULT_WATCHLIST, help="file danh sách IP (mặc định: assets/ip-watchlist.txt)")
    ap.add_argument("--keywords", help="CSV keyword cần gắn cờ IP (chế độ cổng trước brief)")
    ap.add_argument("--column", default="keyword")
    ap.add_argument("--json", help="ghi báo cáo JSON")
    args = ap.parse_args(argv)
    watch = load_watchlist(args.watchlist)

    if args.keywords:
        flagged = []
        with open(args.keywords, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                kw = row.get(args.column, "")
                hits = ip_hits(kw, watch)
                if hits:
                    flagged.append((kw, row.get("volume", ""), ", ".join(hits)))
        print(f"{len(flagged)} keyword khớp danh sách IP")
        for kw, vol, hits in flagged[:100]:
            print(f"  - {kw} (volume {vol}) <- {hits}")
        if args.json:
            with open(args.json, "w", encoding="utf-8") as fh:
                json.dump([{"keyword": k, "volume": v, "match": h} for k, v, h in flagged], fh, ensure_ascii=False, indent=1)
        return 0
    if not args.file:
        ap.error("cần file bài viết hoặc --keywords")
    with open(args.file, encoding="utf-8") as fh:
        text = fh.read()
    findings, waived = scan(text, args.market, watch)
    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    findings.sort(key=lambda f: (order[f["severity"]], f["line"]))
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in order}
    print(f"Thị trường: {args.market} | high={counts['high']} medium={counts['medium']} info={counts['info']} | đã miễn trừ: {len(waived)}")
    for f in findings:
        found = f.get("matched") and " | khớp: " + ", ".join(f["matched"][:6]) or ""
        print(f"  [{f['severity']}] dòng {f['line']} · {f['rule']}: “{f['text']}”{found}\n        {f['message']}\n"
              f"        Nguồn: {f['source']}\n        Cách xử lý: {f['fix']}")
    for w in waived:
        print(f"  [miễn trừ] dòng {w['line']} · {w['rule']}: {w['waiver']}")
    print("Lưu ý: công cụ chỉ gắn cờ, không phải tư vấn pháp lý; claim rủi ro cao cần pháp chế duyệt.")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"findings": findings, "waived": waived}, fh, ensure_ascii=False, indent=1)
    return 1 if counts["high"] else 0


if __name__ == "__main__":
    sys.exit(main())
