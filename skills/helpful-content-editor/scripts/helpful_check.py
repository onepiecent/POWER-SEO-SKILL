#!/usr/bin/env python3
"""Review a blog post against "helpful to the reader" (people-first) criteria. Standard library only.

The script measures what CAN be measured (structure, opening, readability, evidence, signs of writing for search engines,
signs of AI-sounding text, trust signals, US/UK spelling). Parts that need judgement (a point of view of its own, how well
the post covers the reader's questions, honesty) are assessed by Claude or an editor with references/rubric.md.

The score is an internal heuristic for comparing drafts, NOT a Google metric.

Usage:
    helpful_check.py draft.md --market us --post-type gift-guide --keyword "mother's day gifts for grandma"
    helpful_check.py draft.md --json report.json
    helpful_check.py final.md --final        # unresolved placeholders (DATA NEEDED, LINK, TODO) = error

Standard markers in a post:
    [EXPERIENCE: real internal source]  [DATA: original data source]  [DATA NEEDED: ...]  [LINK: topic]  [PRODUCT-SLOT: ...]
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
    t = re.sub(r"^\s*\|.*\|\s*$", "\n", t, flags=re.M)   # tables
    t = re.sub(r"^#{1,6}\s+.*$", "\n", t, flags=re.M)     # headings (keep paragraph boundaries)
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

    # 1. structure
    h1 = re.findall(r"^#\s+(.+)$", text, flags=re.M)
    h2 = re.findall(r"^##\s+(.+)$", text, flags=re.M)
    levels = [len(m) for m in re.findall(r"^(#{1,6})\s", text, flags=re.M)]
    if len(h1) != 1:
        r.add("high", "structure", f"exactly one H1 is needed, found {len(h1)}")
    if len(words) > 800 and len(h2) < 3:
        r.add("medium", "structure", f"a {len(words)}-word post has only {len(h2)} H2s; split it into sections that follow the reader's questions")
    if any(b - a > 1 for a, b in zip(levels, levels[1:])):
        r.add("low", "structure", "heading levels are skipped (for example H2 -> H4)")
    r.metrics.update({"h1": len(h1), "h2": len(h2)})

    # 2. opening (answer early)
    first_h2 = re.search(r"^##\s", text, flags=re.M)
    intro = clean_body(text[:first_h2.start()]) if first_h2 else body
    intro = re.sub(r"^#\s+.*$", "", intro, flags=re.M)
    intro_words = len(intro.split())
    r.metrics["intro_words"] = intro_words
    if intro_words > 150:
        r.add("medium", "answer_first", f"the opening is {intro_words} words before the first H2; get to the point within ~150 words [Convention]")
    if intro_words < 25 and len(words) > 500:
        r.add("low", "answer_first", "the opening is too short to say who the post is for and what it answers")
    first100 = " ".join(intro.split()[:100]).lower()
    for pat in AI_ISMS[:3]:
        if re.search(pat, first100):
            r.add("medium", "answer_first", "the post opens with a generic throat-clearing sentence; go straight to the answer")
            break

    # 3. readability (plain language: short sentences, simple words, active voice)
    syl = sum(syllables(w) for w in words)
    fk = 0.39 * (len(words) / n_sents) + 11.8 * (syl / n_words) - 15.59
    avg_len = len(words) / n_sents
    long_pct = 100 * sum(1 for s in sents if len(s.split()) > 30) / n_sents
    passive_pct = 100 * sum(1 for s in sents if PASSIVE_RX.search(s)) / n_sents
    r.metrics.update({"flesch_kincaid_grade": round(fk, 1), "avg_sentence_words": round(avg_len, 1),
                      "long_sentence_pct": round(long_pct, 1), "passive_pct": round(passive_pct, 1)})
    if fk > 10:
        r.add("medium", "readability", f"Flesch-Kincaid grade {fk:.1f} (> 10): shorten sentences and use simpler words "
                                       "(plainlanguage.gov, GOV.UK style guide)")
    if avg_len > 22:
        r.add("low", "readability", f"average sentence is {avg_len:.0f} words (aim for 15-20)")
    if long_pct > 10:
        r.add("low", "readability", f"{long_pct:.0f}% of sentences are longer than 30 words")
    if passive_pct > 25:
        r.add("low", "readability", f"{passive_pct:.0f}% of sentences are passive; prefer the active voice")
    long_paras = []
    for block in re.split(r"\n\s*\n", text):
        if re.match(r"\s*([-+*]|\d+[.)])\s", block) or block.lstrip().startswith(("#", "|", "```", ">")):
            continue  # lists, tables and headings are not "long paragraphs"
        if len(sentences_of(clean_body(block))) > 5:
            long_paras.append(block)
    if long_paras:
        r.add("low", "readability", f"{len(long_paras)} paragraphs are longer than 5 sentences; split them (2-4 sentences)")

    # 4. evidence and sources
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
              f"{len(unsupported)} sentences contain figures, prices or percentages without a source; add a link to the original source or [DATA NEEDED: ...]",
              " | ".join(unsupported[:3]))

    # 5. real experience / not "commodity" content
    exp_tags = len(re.findall(r"\[EXPERIENCE:", text))
    data_tags = len(re.findall(r"\[DATA:", text))
    first_hand = [m.group(0) for m in FIRST_HAND_RX.finditer(body)]
    r.metrics.update({"experience_tags": exp_tags, "data_tags": data_tags, "first_hand_phrases": len(first_hand)})
    if first_hand and not (exp_tags or data_tags):
        r.add("high", "first_hand", "sentences such as 'we tested/our team...' appear but there is no [EXPERIENCE: source] or [DATA: source]; "
                                    "keep them only if true and backed by evidence (photos, measurements, internal notes)")
    if len(words) > 500 and not (exp_tags or data_tags):
        r.add("medium" if post_type in ("gift-guide", "ideas-list", "choose-guide", "pillar-hub") else "low", "non_commodity",
              "no first-hand experience or original data point yet ([EXPERIENCE:] or [DATA:]); the content risks being 'commodity' "
              "(Google recommends content with its own point of view and first-hand experience)")

    # 6. AI-sounding phrases / cliches
    low = body.lower()
    hits = []
    for pat in AI_ISMS:
        for m in re.finditer(pat, low):
            hits.append(m.group(0))
    r.metrics["ai_ism_hits"] = len(hits)
    if hits:
        per_k = len(hits) / n_words * 1000
        r.add("medium" if per_k > 2 else "low", "voice", f"{len(hits)} cliche or AI-sounding phrases ({per_k:.1f} per 1,000 words): "
              + ", ".join(sorted(set(hits))[:8]))

    # 7. keyword stuffing / writing for search engines first
    if keyword:
        kw = keyword.lower().replace("’", "'")
        count = low.replace("’", "'").count(kw)
        density = count * len(kw.split()) / n_words * 100
        r.metrics["keyword_density_pct"] = round(density, 2)
        if density > 2:
            r.add("medium", "stuffing", f"primary keyword density is {density:.1f}% (> 2%); use synonyms and natural phrasing")
        if h2 and sum(1 for h in h2 if kw in h.lower()) / len(h2) > 0.6:
            r.add("low", "stuffing", "more than 60% of the H2s repeat the whole keyword; headings should follow the reader's questions")
        if kw not in " ".join(h1).lower() and kw not in first100:
            r.add("low", "intent_match", "the primary keyword does not appear in the H1 or the first 100 words")
    dup = {}
    for h in h2:
        key = " ".join(re.findall(r"[a-z]+", h.lower())[:4])
        dup[key] = dup.get(key, 0) + 1
    if any(v > 2 and k for k, v in dup.items()):
        r.add("low", "stuffing", "several H2s start the same way; a sign of a template-built post")

    # 8. trust signals (Who / How / Why)
    has_author = bool(meta.get("author")) or bool(re.search(r"^\s*(by|author|written by)\b.{2,60}$", raw, re.I | re.M))
    has_date = bool(meta.get("updated") or meta.get("date") or re.search(r"(last )?(updated|published)\s*:?\s*\w+", raw, re.I))
    if not has_author:
        r.add("medium", "trust", "no author (byline) found. Google: readers should know who created the content and why")
    if not has_date:
        r.add("low", "trust", "no visible published or updated date found")

    # 9. natural commercial integration
    ctas = CTA_RX.findall(body)
    if len(ctas) > max(1, len(words) // 800):
        r.add("medium", "commercial", f"{len(ctas)} buy-now or urgency sentences; a helpful post does not need 'buy now'")
    if CTA_RX.search(" ".join(intro.split()[:150])):
        r.add("medium", "commercial", "sales call to action in the first 150 words: answer the reader first")
    n_slots = len(re.findall(r"\[PRODUCT-SLOT:", text))
    r.metrics["product_slots"] = n_slots
    if n_slots:
        r.add("low", "commercial", f"{n_slots} [PRODUCT-SLOT]: run product-slot/slot_check.py to check density and placement")

    # 10. spelling and formats by market
    tokens = set(re.findall(r"[a-z]+", low))
    us_hit = sorted(t for t in US_FORMS if t in tokens)
    uk_hit = sorted(t for t in UK_FORMS if t in tokens)
    if market == "us" and uk_hit:
        r.add("medium", "market_spelling", "US post with British spelling: " + ", ".join(uk_hit))
    if market == "uk" and us_hit:
        r.add("medium", "market_spelling", "UK post with American spelling: " + ", ".join(us_hit))
    if us_hit and uk_hit:
        r.add("medium", "market_spelling", f"mixes American ({', '.join(us_hit)}) and British ({', '.join(uk_hit)}) spelling")
    if market == "uk" and "$" in text:
        r.add("low", "market_format", "UK post contains a $ sign; use £ and prices confirmed for the UK")
    if market == "us" and "£" in text:
        r.add("low", "market_format", "US post contains a £ sign")

    # 11. unresolved placeholders
    ph = PLACEHOLDER_RX.findall(text)
    if ph:
        r.add("high" if final else "low", "placeholders",
              f"{len(PLACEHOLDER_RX.findall(text))} unresolved placeholders ([DATA NEEDED]/[LINK]/TODO)"
              + (" – a post must not be published while placeholders remain" if final else ""))
    return r


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--market", choices=["us", "uk", "both"], default="both")
    ap.add_argument("--post-type", default="generic")
    ap.add_argument("--keyword", default="")
    ap.add_argument("--final", action="store_true", help="version about to be published: placeholders are errors")
    ap.add_argument("--json", help="write a JSON report")
    args = ap.parse_args(argv)

    with open(args.file, encoding="utf-8") as fh:
        raw = fh.read()
    rep = run_checks(raw, args.market, args.post_type, args.keyword, args.final)
    score = max(0.0, 100 - sum(SEVERITY_COST[f["severity"]] for f in rep.findings))
    band = "ready for a human edit" if score >= 85 else "needs revision" if score >= 70 else "rewrite most of it"
    print(f"Heuristic score: {score:.0f}/100 ({band}) – NOT a Google score")
    print("Metrics: " + ", ".join(f"{k}={v}" for k, v in rep.metrics.items()))
    order = {"high": 0, "medium": 1, "low": 2}
    for f in sorted(rep.findings, key=lambda f: order[f["severity"]]):
        print(f"  [{f['severity']}] {f['rule']}: {f['message']}" + (f"\n        ↳ {f['where']}" if f["where"] else ""))
    if not rep.findings:
        print("  No automatic findings. You still need to assess the draft with references/rubric.md (own point of view, honesty, coverage).")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"score": score, "metrics": rep.metrics, "findings": rep.findings}, fh, ensure_ascii=False, indent=1)
    return 1 if any(f["severity"] == "high" for f in rep.findings) else 0


if __name__ == "__main__":
    sys.exit(main())
