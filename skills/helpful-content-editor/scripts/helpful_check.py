#!/usr/bin/env python3
"""Soát bài blog theo tiêu chí "hữu ích cho người đọc" (people-first). Chỉ dùng thư viện chuẩn.

Script đo phần ĐO ĐƯỢC (cấu trúc, mở bài, độ đọc, bằng chứng, dấu hiệu viết cho công cụ tìm kiếm,
dấu hiệu giọng AI, tín hiệu tin cậy, chính tả US/UK). Phần cần phán đoán (góc nhìn riêng, mức bao phủ
câu hỏi của người đọc, tính trung thực) do Claude/biên tập viên đánh giá theo references/rubric.md.

Điểm là heuristic nội bộ để so sánh giữa các bản nháp, KHÔNG phải số đo của Google.

Chạy:
    helpful_check.py draft.md --market us --post-type gift-guide --keyword "mother's day gifts for grandma"
    helpful_check.py draft.md --json report.json
    helpful_check.py final.md --final        # placeholder chưa xử lý (DATA NEEDED, LINK, TODO) = lỗi

Marker chuẩn trong bài:
    [EXPERIENCE: nguồn nội bộ thật]  [DATA: nguồn số liệu gốc]  [DATA NEEDED: ...]  [LINK: chủ đề]  [PRODUCT-SLOT: ...]
"""
from __future__ import annotations

import argparse
import json
import re
import sys

AI_ISMS = [
    r"in today'?s (fast[- ]paced|digital|modern) (world|age|landscape)", r"in the ever[- ](evolving|changing)",
    r"\bdelve[sd]? (into|deeper)\b", r"\btapestry\b", r"\bunlock(ing)? the (power|secrets?|potential)\b",
    r"\belevate your\b", r"\bgame[- ]changer\b", r"navigat(e|ing) the (world|landscape|complexities) of",
    r"\blook no further\b", r"it'?s (important|worth) (to note|noting)( that)?", r"\bin conclusion\b",
    r"at the end of the day", r"\ba testament to\b", r"\bembark on\b", r"\bseamless(ly)?\b", r"\brobust\b",
    r"\bleverag(e|ing)\b", r"\bdive (right )?into\b", r"when it comes to", r"whether you'?re .{3,40} or .{3,40},",
    r"\bin the realm of\b", r"\bvibrant\b", r"\bbustling\b", r"\bmeticulous(ly)?\b", r"\bpivotal\b",
    r"\bnot just .{3,40}, but\b", r"\bperfect (gift|choice|way) for (everyone|any)\b",
]
CTA_RX = re.compile(r"\b(buy now|shop now|order now|click here|limited time|act now|don'?t miss (out)?|hurry|grab yours)\b", re.I)
FIRST_HAND_RX = re.compile(r"\b(we|our team|i)\s+(tested|tried|measured|compared|surveyed|interviewed|washed|wore|asked)\b|"
                           r"\bin our (tests?|experience)\b", re.I)
NUMBER_CLAIM_RX = re.compile(r"(\d[\d,.]*\s?%|[$£€]\s?\d|\b\d[\d,]{2,}\b|\b\d+(\.\d+)?\s?(million|billion|thousand|percent|per cent)\b)", re.I)
YEAR_ONLY_RX = re.compile(r"^(19|20)\d\d$")
PLACEHOLDER_RX = re.compile(r"\[(DATA NEEDED|LINK|TODO)[^\]]*\]|\bTODO\b|lorem ipsum", re.I)
US_FORMS = ["color", "organize", "personalized", "favorite", "mom", "center", "gray", "jewelry", "sneakers", "customized",
            "humor", "program", "neighbor", "realize", "apparel"]
UK_FORMS = ["colour", "organise", "personalised", "favourite", "mum", "centre", "grey", "jewellery", "trainers", "customised",
            "humour", "programme", "neighbour", "realise"]
PASSIVE_RX = re.compile(r"\b(am|is|are|was|were|be|been|being)\s+(\w+ly\s+)?(\w+ed|\w+en|made|done|given|known|seen|shown|written|taken|built|sold|used|found)\b", re.I)
SEVERITY_COST = {"high": 8, "medium": 4, "low": 1.5}


# --------------------------------------------------------------------------- text prep
def split_front_matter(text: str) -> tuple[dict, str]:
    meta: dict = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip().lower()] = v.strip()
            text = text[end + 4:]
    return meta, text


def clean_body(text: str) -> str:
    t = re.sub(r"```.*?```", " ", text, flags=re.S)
    t = re.sub(r"\[(PRODUCT-SLOT|EXPERIENCE|DATA NEEDED|DATA|LINK|CLAIM-OK|SOURCE)[^\]]*\]", " ", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"^\s*\|.*\|\s*$", "\n", t, flags=re.M)   # bảng
    t = re.sub(r"^#{1,6}\s+.*$", "\n", t, flags=re.M)     # tiêu đề (giữ ranh giới đoạn)
    t = re.sub(r"[*_`>]+", "", t)
    t = re.sub(r"^\s*([-+*]|\d+[.)])\s+", "", t, flags=re.M)
    return t


def sentences_of(body: str) -> list[str]:
    out = []
    for para in re.split(r"\n+", body):
        para = para.strip()
        if not para:
            continue
        out += [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(])", para) if s.strip()]
    return out


def syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    n = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and not w.endswith(("le", "ee")) and n > 1:
        n -= 1
    return max(1, n)


# --------------------------------------------------------------------------- checks
class Report:
    def __init__(self):
        self.findings: list[dict] = []
        self.metrics: dict = {}

    def add(self, severity: str, rule: str, message: str, where: str = "") -> None:
        self.findings.append({"severity": severity, "rule": rule, "message": message, "where": where})


def run_checks(raw: str, market: str, post_type: str, keyword: str, final: bool) -> Report:
    r = Report()
    meta, text = split_front_matter(raw)
    body = clean_body(text)
    sents = sentences_of(body)
    words = re.findall(r"[A-Za-z0-9'’-]+", body)
    n_words, n_sents = max(1, len(words)), max(1, len(sents))
    r.metrics["words"] = len(words)

    # 1. cấu trúc
    h1 = re.findall(r"^#\s+(.+)$", text, flags=re.M)
    h2 = re.findall(r"^##\s+(.+)$", text, flags=re.M)
    levels = [len(m) for m in re.findall(r"^(#{1,6})\s", text, flags=re.M)]
    if len(h1) != 1:
        r.add("high", "structure", f"cần đúng 1 H1, hiện có {len(h1)}")
    if len(words) > 800 and len(h2) < 3:
        r.add("medium", "structure", f"bài {len(words)} từ chỉ có {len(h2)} H2; chia mục theo câu hỏi của người đọc")
    if any(b - a > 1 for a, b in zip(levels, levels[1:])):
        r.add("low", "structure", "nhảy cấp tiêu đề (vd H2 -> H4)")
    r.metrics.update({"h1": len(h1), "h2": len(h2)})

    # 2. mở bài (trả lời sớm)
    first_h2 = re.search(r"^##\s", text, flags=re.M)
    intro = clean_body(text[:first_h2.start()]) if first_h2 else body
    intro = re.sub(r"^#\s+.*$", "", intro, flags=re.M)
    intro_words = len(intro.split())
    r.metrics["intro_words"] = intro_words
    if intro_words > 150:
        r.add("medium", "answer_first", f"mở bài {intro_words} từ trước H2 đầu tiên; nên vào việc trong ~150 từ [Quy ước]")
    if intro_words < 25 and len(words) > 500:
        r.add("low", "answer_first", "mở bài quá ngắn để nói bài dành cho ai và trả lời được gì")
    first100 = " ".join(intro.split()[:100]).lower()
    for pat in AI_ISMS[:3]:
        if re.search(pat, first100):
            r.add("medium", "answer_first", "mở bài bằng câu rào đón chung chung; đi thẳng vào câu trả lời")
            break

    # 3. độ đọc (plain language: câu ngắn, từ đơn giản, chủ động)
    syl = sum(syllables(w) for w in words)
    fk = 0.39 * (len(words) / n_sents) + 11.8 * (syl / n_words) - 15.59
    avg_len = len(words) / n_sents
    long_pct = 100 * sum(1 for s in sents if len(s.split()) > 30) / n_sents
    passive_pct = 100 * sum(1 for s in sents if PASSIVE_RX.search(s)) / n_sents
    r.metrics.update({"flesch_kincaid_grade": round(fk, 1), "avg_sentence_words": round(avg_len, 1),
                      "long_sentence_pct": round(long_pct, 1), "passive_pct": round(passive_pct, 1)})
    if fk > 10:
        r.add("medium", "readability", f"Flesch-Kincaid grade {fk:.1f} (> 10): rút ngắn câu, dùng từ đơn giản "
                                       "(plainlanguage.gov, GOV.UK style guide)")
    if avg_len > 22:
        r.add("low", "readability", f"câu trung bình {avg_len:.0f} từ (nên 15-20)")
    if long_pct > 10:
        r.add("low", "readability", f"{long_pct:.0f}% câu dài hơn 30 từ")
    if passive_pct > 25:
        r.add("low", "readability", f"{passive_pct:.0f}% câu bị động; ưu tiên chủ động")
    long_paras = []
    for block in re.split(r"\n\s*\n", text):
        if re.match(r"\s*([-+*]|\d+[.)])\s", block) or block.lstrip().startswith(("#", "|", "```", ">")):
            continue  # danh sách, bảng, tiêu đề không phải "đoạn dài"
        if len(sentences_of(clean_body(block))) > 5:
            long_paras.append(block)
    if long_paras:
        r.add("low", "readability", f"{len(long_paras)} đoạn dài hơn 5 câu; tách đoạn (2-4 câu)")

    # 4. bằng chứng và nguồn
    unsupported = []
    for para in re.split(r"\n\s*\n", text):
        has_source = bool(re.search(r"\]\(https?://|\[(SOURCE|DATA|DATA NEEDED)[:\]]", para))
        for s in sentences_of(clean_body(para)):
            nums = [m.group(0) for m in NUMBER_CLAIM_RX.finditer(s)]
            if nums and not all(YEAR_ONLY_RX.match(n.strip()) for n in nums) and not has_source:
                unsupported.append(s[:140])
    ext_links = len(re.findall(r"\]\(https?://", text))
    r.metrics.update({"external_links": ext_links, "unsupported_number_sentences": len(unsupported)})
    if unsupported:
        r.add("high" if len(unsupported) >= 3 else "medium", "evidence",
              f"{len(unsupported)} câu có số liệu/giá/% nhưng không có nguồn; thêm link nguồn gốc hoặc [DATA NEEDED: ...]",
              " | ".join(unsupported[:3]))

    # 5. kinh nghiệm thật / không "hàng phổ thông"
    exp_tags = len(re.findall(r"\[EXPERIENCE:", text))
    data_tags = len(re.findall(r"\[DATA:", text))
    first_hand = [m.group(0) for m in FIRST_HAND_RX.finditer(body)]
    r.metrics.update({"experience_tags": exp_tags, "data_tags": data_tags, "first_hand_phrases": len(first_hand)})
    if first_hand and not (exp_tags or data_tags):
        r.add("high", "first_hand", "có câu kiểu 'we tested/our team...' nhưng không có [EXPERIENCE: nguồn] hoặc [DATA: nguồn]; "
                                    "chỉ giữ nếu thật và có bằng chứng (ảnh, số đo, ghi chú nội bộ)")
    if len(words) > 500 and not (exp_tags or data_tags):
        r.add("medium" if post_type in ("gift-guide", "ideas-list", "choose-guide", "pillar-hub") else "low", "non_commodity",
              "chưa có điểm kinh nghiệm/dữ liệu gốc nào ([EXPERIENCE:] hoặc [DATA:]); nội dung dễ rơi vào 'hàng phổ thông' "
              "(Google khuyến nghị nội dung có góc nhìn riêng, kinh nghiệm trực tiếp)")

    # 6. giọng AI / sáo ngữ
    low = body.lower()
    hits = []
    for pat in AI_ISMS:
        for m in re.finditer(pat, low):
            hits.append(m.group(0))
    r.metrics["ai_ism_hits"] = len(hits)
    if hits:
        per_k = len(hits) / n_words * 1000
        r.add("medium" if per_k > 2 else "low", "voice", f"{len(hits)} cụm sáo rỗng/giọng AI ({per_k:.1f}/1.000 từ): "
              + ", ".join(sorted(set(hits))[:8]))

    # 7. nhồi từ khóa / viết cho công cụ tìm kiếm trước
    if keyword:
        kw = keyword.lower().replace("’", "'")
        count = low.replace("’", "'").count(kw)
        density = count * len(kw.split()) / n_words * 100
        r.metrics["keyword_density_pct"] = round(density, 2)
        if density > 2:
            r.add("medium", "stuffing", f"mật độ từ khóa chính {density:.1f}% (> 2%); dùng đồng nghĩa và diễn đạt tự nhiên")
        if h2 and sum(1 for h in h2 if kw in h.lower()) / len(h2) > 0.6:
            r.add("low", "stuffing", "hơn 60% H2 chứa nguyên cụm từ khóa; tiêu đề nên theo câu hỏi người đọc")
        if kw not in " ".join(h1).lower() and kw not in first100:
            r.add("low", "intent_match", "từ khóa chính không xuất hiện ở H1 hoặc 100 từ đầu")
    dup = {}
    for h in h2:
        key = " ".join(re.findall(r"[a-z]+", h.lower())[:4])
        dup[key] = dup.get(key, 0) + 1
    if any(v > 2 and k for k, v in dup.items()):
        r.add("low", "stuffing", "nhiều H2 mở đầu giống nhau; dấu hiệu bài ghép theo khuôn")

    # 8. tín hiệu tin cậy (Who / How / Why)
    has_author = bool(meta.get("author")) or bool(re.search(r"^\s*(by|author|written by)\b.{2,60}$", raw, re.I | re.M))
    has_date = bool(meta.get("updated") or meta.get("date") or re.search(r"(last )?(updated|published)\s*:?\s*\w+", raw, re.I))
    if not has_author:
        r.add("medium", "trust", "chưa thấy tác giả (byline). Google: người đọc nên biết ai tạo nội dung và vì sao")
    if not has_date:
        r.add("low", "trust", "chưa thấy ngày đăng/cập nhật hiển thị")

    # 9. tích hợp thương mại tự nhiên
    ctas = CTA_RX.findall(body)
    if len(ctas) > max(1, len(words) // 800):
        r.add("medium", "commercial", f"{len(ctas)} câu kêu gọi mua/hối thúc; bài hữu ích không cần 'buy now'")
    if CTA_RX.search(" ".join(intro.split()[:150])):
        r.add("medium", "commercial", "CTA bán hàng trong 150 từ đầu: trả lời người đọc trước")
    n_slots = len(re.findall(r"\[PRODUCT-SLOT:", text))
    r.metrics["product_slots"] = n_slots
    if n_slots:
        r.add("low", "commercial", f"{n_slots} [PRODUCT-SLOT]: chạy product-slot/slot_check.py để kiểm mật độ và vị trí")

    # 10. chính tả/định dạng theo thị trường
    tokens = set(re.findall(r"[a-z]+", low))
    us_hit = sorted(t for t in US_FORMS if t in tokens)
    uk_hit = sorted(t for t in UK_FORMS if t in tokens)
    if market == "us" and uk_hit:
        r.add("medium", "market_spelling", "bài US nhưng có chính tả Anh: " + ", ".join(uk_hit))
    if market == "uk" and us_hit:
        r.add("medium", "market_spelling", "bài UK nhưng có chính tả Mỹ: " + ", ".join(us_hit))
    if us_hit and uk_hit:
        r.add("medium", "market_spelling", f"trộn chính tả Mỹ ({', '.join(us_hit)}) và Anh ({', '.join(uk_hit)})")
    if market == "uk" and "$" in text:
        r.add("low", "market_format", "bài UK có ký hiệu $; dùng £ và giá đã xác nhận cho UK")
    if market == "us" and "£" in text:
        r.add("low", "market_format", "bài US có ký hiệu £")

    # 11. placeholder chưa xử lý
    ph = PLACEHOLDER_RX.findall(text)
    if ph:
        r.add("high" if final else "low", "placeholders",
              f"{len(PLACEHOLDER_RX.findall(text))} placeholder chưa xử lý ([DATA NEEDED]/[LINK]/TODO)"
              + (" – không được đăng khi còn placeholder" if final else ""))
    return r


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--market", choices=["us", "uk", "both"], default="both")
    ap.add_argument("--post-type", default="generic")
    ap.add_argument("--keyword", default="")
    ap.add_argument("--final", action="store_true", help="bản chuẩn bị đăng: placeholder = lỗi")
    ap.add_argument("--json", help="ghi báo cáo JSON")
    args = ap.parse_args(argv)

    with open(args.file, encoding="utf-8") as fh:
        raw = fh.read()
    rep = run_checks(raw, args.market, args.post_type, args.keyword, args.final)
    score = max(0.0, 100 - sum(SEVERITY_COST[f["severity"]] for f in rep.findings))
    band = "sẵn sàng cho biên tập người" if score >= 85 else "cần sửa" if score >= 70 else "viết lại phần lớn"
    print(f"Điểm heuristic: {score:.0f}/100 ({band}) – KHÔNG phải điểm của Google")
    print("Số đo: " + ", ".join(f"{k}={v}" for k, v in rep.metrics.items()))
    order = {"high": 0, "medium": 1, "low": 2}
    for f in sorted(rep.findings, key=lambda f: order[f["severity"]]):
        print(f"  [{f['severity']}] {f['rule']}: {f['message']}" + (f"\n        ↳ {f['where']}" if f["where"] else ""))
    if not rep.findings:
        print("  Không có phát hiện tự động. Vẫn cần đánh giá bằng references/rubric.md (góc nhìn riêng, trung thực, mức bao phủ).")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"score": score, "metrics": rep.metrics, "findings": rep.findings}, fh, ensure_ascii=False, indent=1)
    return 1 if any(f["severity"] == "high" for f in rep.findings) else 0


if __name__ == "__main__":
    sys.exit(main())
