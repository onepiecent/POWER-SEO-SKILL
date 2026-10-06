#!/usr/bin/env python3
"""Check US/UK blog posts for legally or advertising-risky claims, and flag IP names in keyword lists.
Standard library only. NOT legal advice: the tool only raises flags so that a person or legal can decide.

Usage:
    claims_check.py draft.md --market us
    claims_check.py draft.md --market uk --json report.json
    claims_check.py --keywords keyword-map.csv --column keyword      # IP gate before writing a brief

A claim that has been reviewed and approved by someone with authority can carry a marker in the same paragraph: [CLAIM-OK: reason; approver; date]
(that paragraph is skipped and listed under "waived").
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

FTC_REVIEWS = "FTC 16 CFR Part 465 (fake reviews and testimonials, in force since 21 Oct 2024)"
CMA_REVIEWS = "CMA DMCC Act 2024: fake and undisclosed incentivised reviews banned since April 2025 (CMA208)"
FTC_SHIP = "FTC Mail, Internet, or Telephone Order Merchandise Rule: shipping-time claims need a reasonable basis"
FTC_GREEN = "FTC Green Guides (16 CFR 260); CMA Green Claims Code"
ASA_CAP = "ASA/CAP Code: objective claims must be substantiated; content on a seller's own website that is directly connected with the sale of goods may fall within the CAP Code"

# id, severity, regex (on the original text, case-insensitive), markets, source, message, fix
RULES = [
    ("delivery_promise", "high",
     r"\b(arrives? by|delivered? (by|in|within)|ships? (in|within|by)|fast (shipping|delivery)|next[- ]day|same[- ]day|"
     r"guaranteed delivery|order by|last order date|cut-?off|overnight (shipping|delivery)|express (shipping|delivery)|"
     r"before (christmas|mother'?s day|mothering sunday|father'?s day|valentine'?s( day)?|halloween|easter))\b",
     ("us", "uk"), FTC_SHIP + "; " + ASA_CAP,
     "A delivery-time promise or order deadline needs confirmed operations data and the conditions that go with it.",
     "Replace with [DATA NEEDED: order deadline confirmed by operations, confirmation date] or remove."),
    ("review_testimonial", "high",
     r"\b(customers? (love|say|rave|report)|\d(\.\d)?[- ]star|five[- ]star|reviews? (say|show)|rated \d(\.\d)?|"
     r"thousands of (happy )?customers|loved by|trusted by|best[- ]?sellers?|most popular|top[- ]selling|selling fast|hot seller)\b",
     ("us", "uk"), FTC_REVIEWS + "; " + CMA_REVIEWS,
     "Reviews and popularity claims must rest on real, current data. Fake reviews (including AI-generated ones) and insider reviews that do not disclose the relationship are prohibited.",
     "Keep only if you quote real figures with a source and date; otherwise remove. Add [DATA NEEDED: review source, date]."),
    ("eco_general", "high",
     r"\b(eco[- ]?friendly|sustainabl[ey]|environmentally friendly|planet[- ]friendly|climate[- ]friendly|"
     r"carbon[- ]neutral|net[- ]zero|zero waste|go green|green (product|choice|alternative|living|credentials))\b",
     ("us", "uk"), FTC_GREEN,
     "General environmental claims (eco-friendly, sustainable...) are very hard to substantiate; the Green Guides advise against using them without specific qualification.",
     "State a specific, measurable attribute with evidence (for example a verified recycled-content share) or remove it."),
    ("eco_specific", "medium",
     r"\b(recycled|recyclable|biodegradable|compostable|organic|vegan|cruelty[- ]free|non[- ]toxic|ethically (made|sourced))\b",
     ("us", "uk"), FTC_GREEN,
     "Specific material or environmental claims need a certification or supplier documentation.",
     "State the certification or source (for example certificate name, percentage) with [DATA NEEDED: supplier documentation] or remove it."),
    ("health_claim", "high",
     r"\b(cures?|clinically (proven|tested)|doctor[- ]recommended|medically (proven|tested|approved)|"
     r"anti[- ]?(bacterial|microbial|viral)|therapeutic|heals?|(reduces?|relieves?) (stress|anxiety|pain|symptoms))\b",
     ("us", "uk"), ASA_CAP + "; FTC Act s.5 (health claims need scientific evidence)",
     "Health or medical claims about a product need sufficiently strong scientific evidence.",
     "Remove, or talk about the emotional experience of the gift instead of medical effects."),
    ("superlative_guarantee", "medium",
     r"(\b(our|we|printerval)\b[^.\n]{0,40}\bbest\b|\bbest (price|quality|seller|selling|deal|value|in the (world|business|industry))\b|"
     r"(?<![\w])#1(?![\w])|\bnumber one\b|\bguarantee[sd]?\b|\bunbeatable\b|\brisk[- ]free\b|"
     r"\b100% (satisfaction|safe|natural|organic|cotton)\b|\blowest price\b|\bprice match\b)",
     ("us", "uk"), ASA_CAP + "; FTC Act s.5",
     "Absolute comparisons and guarantees are objective claims: they need evidence or clear conditions.",
     "Write it as an editorial choice with criteria ('our pick for ... because ...'), or cite evidence."),
    ("price_offer", "medium",
     r"(\b\d+\s?% off\b|\bfree shipping\b|\bfree returns?\b|\bon sale\b|\bdiscount(ed)?\b|\bcoupon\b|\bpromo code\b|"
     r"\b(save|from|only|just) [$£]\s?\d)",
     ("us", "uk"), "FTC Act s.5; CMA/ASA: price and offer statements must be accurate and still valid",
     "Prices and offers change and must be confirmed by the commercial team; do not fix them in an evergreen post.",
     "Remove the specific price or write 'as of <date>' with [DATA NEEDED: price confirmed by the commercial team]."),
    ("policy_claim", "medium",
     r"\b(money[- ]back|\d+[- ]day (returns?|guarantee|refund)|lifetime warranty|satisfaction guarantee)\b",
     ("us", "uk"), "FTC/CMA: policy claims must match the real policy",
     "Return or warranty claims must match the current policy exactly.",
     "Quote the policy accurately and link to the policy page, or remove the claim."),
    ("made_in", "high",
     r"\bmade in (the )?(usa|u\.s\.a\.?|america|united states|uk|britain)\b",
     ("us", "uk"), "FTC 'Made in USA' standard (all or virtually all of the product made in the US); CMA/ASA for origin claims",
     "Origin claims must be true (print-on-demand products are usually made to order by several factories in several countries).",
     "Keep only when the supply chain confirms it for the exact product mentioned."),
    ("handmade_claim", "low",
     r"\b(handmade|hand[- ]made|handcrafted|artisan[- ]made)\b",
     ("us", "uk"), "CMA/ASA/FTC: handmade claims must be true",
     "If this is about Printerval's OWN products, 'handmade' may not be true for print-on-demand; ignore it if the topic is simply DIY.",
     "Confirm with operations or use accurate wording (for example 'made to order')."),
    ("first_hand_claim", "medium",
     r"\b(we|our team|i)\s+(tested|tried|measured|compared|reviewed|interviewed|surveyed|washed|wore)\b|\bin our (tests?|experience|lab)\b",
     ("us", "uk"), "Google (review-writing guidance: evidence of first-hand experience); " + FTC_REVIEWS.split(" (")[0] + " (no fabricated experience)",
     "A claim of first-hand experience must be real and backed by evidence.",
     "Add [EXPERIENCE: real internal source] in the same paragraph, or rewrite so it does not claim first-hand experience."),
    ("disclosure", "medium",
     r"\b(affiliate|sponsored|paid partnership|in partnership with|gifted|sent (to us )?for free|we may earn)\b",
     ("us", "uk"), "FTC Endorsement Guides; ASA/CAP: material connections must be disclosed clearly and close to the content",
     "Content with a commercial relationship or sponsorship needs a clear disclosure at the top of the post and near the relevant text.",
     "Add a disclosure line at the top of the post (for example 'This post contains affiliate links...') that matches reality."),
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
                    "USPTO/UK IPO: risk of trademark confusion; personality rights for artist names",
                    "message": "Brand, franchise or artist names may be protected. Mentioning one to give honest information is different from "
                               "using the name to sell or promote products that carry it.",
                    "fix": "Ask legal/IP: keep it to an informational mention, or remove it from the title, H2s, anchors and product descriptions."}
            (waived if ok else findings).append({**item, **({"waiver": ok.group(1).strip()} if ok else {})})
    if market in ("uk", "both") and "[PRODUCT-SLOT:" in text:
        findings.append({"rule": "uk_remit_note", "severity": "info", "line": 0, "text": "[PRODUCT-SLOT]",
                         "source": ASA_CAP, "message": "A UK post mentions the seller's own products: the ASA may treat content directly connected with the sale of goods "
                         "as advertising within the CAP Code.",
                         "fix": "Every objective claim in the post must be substantiated; confirm with legal how to disclose."})
    return findings, waived


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?", help="blog post (.md/.txt) to check")
    ap.add_argument("--market", choices=["us", "uk", "both"], default="both")
    ap.add_argument("--watchlist", default=DEFAULT_WATCHLIST, help="IP list file (default: assets/ip-watchlist.txt)")
    ap.add_argument("--keywords", help="CSV of keywords to flag for IP (gate before writing a brief)")
    ap.add_argument("--column", default="keyword")
    ap.add_argument("--json", help="write a JSON report")
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
        print(f"{len(flagged)} keywords match the IP list")
        for kw, vol, hits in flagged[:100]:
            print(f"  - {kw} (volume {vol}) <- {hits}")
        if args.json:
            with open(args.json, "w", encoding="utf-8") as fh:
                json.dump([{"keyword": k, "volume": v, "match": h} for k, v, h in flagged], fh, ensure_ascii=False, indent=1)
        return 0
    if not args.file:
        ap.error("a blog post file or --keywords is required")
    with open(args.file, encoding="utf-8") as fh:
        text = fh.read()
    findings, waived = scan(text, args.market, watch)
    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    findings.sort(key=lambda f: (order[f["severity"]], f["line"]))
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in order}
    print(f"Market: {args.market} | high={counts['high']} medium={counts['medium']} info={counts['info']} | waived: {len(waived)}")
    for f in findings:
        found = f.get("matched") and " | matched: " + ", ".join(f["matched"][:6]) or ""
        print(f"  [{f['severity']}] line {f['line']} · {f['rule']}: “{f['text']}”{found}\n        {f['message']}\n"
              f"        Source: {f['source']}\n        What to do: {f['fix']}")
    for w in waived:
        print(f"  [waived] line {w['line']} · {w['rule']}: {w['waiver']}")
    print("Note: the tool only raises flags and is not legal advice; high-risk claims need legal review.")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"findings": findings, "waived": waived}, fh, ensure_ascii=False, indent=1)
    return 1 if counts["high"] else 0


if __name__ == "__main__":
    sys.exit(main())
