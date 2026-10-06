#!/usr/bin/env python3
"""Check and export the [PRODUCT-SLOT] markers in a blog post. Standard library only.

Slot convention (the writer leaves them, the content team replaces them with real links):
    [PRODUCT-SLOT: personalized pet-portrait mug | context: gift for a dog mom | why: she sees her own dog on it]
  - first field: product type / idea (NO URL)
  - context: the reader's situation that the product solves
  - why: why the product fits that situation (about the reader, not a sales slogan)
  - alt (optional): an alternative

Usage:
    slot_check.py draft.md --post-type gift-guide
    slot_check.py draft.md --export slots.csv        # hand-off to the content team
    slot_check.py draft.md --strip preview.md        # read the post WITHOUT products: is it still useful?
    slot_check.py final.md --final                   # before publishing: no slot may remain

Thresholds are an editorial CONVENTION (goal: mention products naturally, and the post stays useful with every slot removed), not a Google rule.
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
# (max slots per 1,000 words, number of opening words that must have no slot)
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
                issues.append(("error", s["id"], f"missing field '{f}:'"))
        if URL_RX.search(s["product"] + s["context"] + s["why"] + s["alt"]):
            issues.append(("error", s["id"], "URL inside a slot: the content team adds links, the writer does not"))
        if s["why"] and len(s["why"].split()) < 5:
            issues.append(("warn", s["id"], "'why' is too short; explain why it fits the reader's situation"))
        if PROMO_RX.search(s["why"] + " " + s["product"]):
            issues.append(("warn", s["id"], "promotional or absolute-comparison wording in the slot; describe the benefit to the reader instead of a slogan"))
        if s["words_before"] < intro_words:
            issues.append(("warn", s["id"], f"slot sits within the first {intro_words} words: answer the reader first, mention products later"))
    density = len(slots) / total * 1000
    if density > max_per_1000:
        issues.append(("warn", "-", f"density {density:.1f} slots per 1,000 words exceeds the reference {max_per_1000} for '{post_type}'"))
    if len(slots) >= 3:
        tail = sum(1 for s in slots if s["words_before"] > 0.8 * total)
        if tail / len(slots) > 0.5:
            issues.append(("warn", "-", "more than half of the slots are in the last 20% of the post: looks like an ad bolted on"))
    for a, b in zip(slots, slots[1:]):
        if b["words_before"] - a["words_before"] < 60:
            issues.append(("warn", f"{a['id']}/{b['id']}", "two slots less than 60 words apart: products are bunched up"))
    return slots, issues, total, density


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--post-type", default="generic", choices=sorted(LIMITS))
    ap.add_argument("--export", help="write a hand-off CSV for the content team")
    ap.add_argument("--strip", help="write a copy of the post with every slot removed to check that it stands on its own")
    ap.add_argument("--final", action="store_true", help="before publishing: fail if any slot remains")
    args = ap.parse_args(argv)

    with open(args.file, encoding="utf-8") as fh:
        text = fh.read()
    slots, issues, total, density = analyse(text, args.post_type)
    print(f"{len(slots)} slots / {total:,} words ({density:.1f} slots per 1,000 words), post type: {args.post_type}")
    for sev, sid, msg in sorted(issues, key=lambda i: (i[0] != "error", i[1])):
        print(f"  [{sev}] {sid}: {msg}")
    if args.final and slots:
        print(f"  [error] --final: {len(slots)} slots have not been replaced with a real link or content yet")
        issues.append(("error", "-", "slots remain with --final"))
    if args.export:
        with open(args.export, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["slot_id", "section", "product_idea", "reader_context", "why_it_helps", "alternative",
                        "approx_word_position", "line", "surrounding_text", "link_added(Y/N)", "link_or_note"])
            for s in slots:
                w.writerow([s["id"], s["section"], s["product"], s["context"], s["why"], s["alt"], s["words_before"],
                            s["line"], s["context_text"], "", ""])
        print(f"Exported {len(slots)} slots -> {args.export}")
    if args.strip:
        clean = re.sub(r"[ \t]{2,}", " ", SLOT_RX.sub("", text))
        clean = re.sub(r"[ \t]+([.,;:!?])", r"\1", clean)
        with open(args.strip, "w", encoding="utf-8") as fh:
            fh.write(clean)
        print(f"Wrote the version without slots -> {args.strip} (read it again: is the post still complete and useful?)")
    return 1 if any(i[0] == "error" for i in issues) else 0


if __name__ == "__main__":
    sys.exit(main())
