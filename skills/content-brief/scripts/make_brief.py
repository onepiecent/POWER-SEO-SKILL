#!/usr/bin/env python3
"""Generate content briefs (in English, ready to hand to a writer or AI) from topic-map.csv. Standard library only.

Filled in AUTOMATICALLY: metadata, keywords, outline by post type, internal links (from link-plan.csv), product-slot plan,
compliance flags, publish deadline (from seasonal-plan.csv). Parts that a person or Claude must fill in after reviewing the real SERP are marked
[TO FILL] (what competitors miss, Printerval's real first-hand angle, sources to cite).

Usage:
    make_brief.py --topic-map outputs/topic-map.csv --link-plan outputs/link-plan.csv --bucket A --out outputs/briefs
    make_brief.py --topic-map outputs/topic-map.csv --slug mothers-day-gifts-for-grandma
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FORMATS_DIR = os.path.join(HERE, "..", "assets", "formats")
READER_JOB = {
    "inspire": "find options they can feel confident about for a specific person, situation and budget",
    "choose": "decide between options and feel sure of the decision",
    "how_to": "complete a task correctly and avoid ruining something",
    "solve": "fix or avoid a specific problem",
    "copy_ideas": "find words that fit a person, tone and place, and use them right away",
    "info": "get a correct answer immediately and understand it well enough to act",
}
FORMAT_FILE = {"gift-guide": "gift-guide", "ideas-list": "ideas-list", "choose-guide": "choose-guide", "how-to": "how-to",
               "explainer": "explainer", "copy-ideas": "copy-ideas", "pillar-hub": "pillar-hub"}
SLOT_RANGE = {"gift-guide": "about one per product-based idea (max ~60% of ideas), none in the intro",
              "ideas-list": "at most one per theme group", "choose-guide": "one per named option, only where it helps",
              "how-to": "0-2, only for items needed to finish the task", "explainer": "0-1",
              "copy-ideas": "0-2", "pillar-hub": "up to one per cluster summary, none in the intro"}
FLAG_RULES = [
    (re.compile(r"\b(shipping|delivery|deliver|arrive|arrival|order by|cut-?off)\b", re.I),
     "DELIVERY: no delivery times or order-by dates unless the operations team confirms them with a date "
     "(FTC Mail/Internet Order Merchandise Rule needs a reasonable basis; CMA/ASA expect substantiation). Use [DATA NEEDED: ...]."),
    (re.compile(r"\b(price|prices|cheap|sale|discount|coupon|deal|deals|free shipping|% off)\b", re.I),
     "PRICE/OFFER: do not state live prices or offers; the commercial team owns them."),
    (re.compile(r"\b(eco|sustainable|organic|recycled|biodegradable|vegan|green)\b", re.I),
     "ENVIRONMENT: avoid general claims (eco-friendly, sustainable); specific claims need supplier documentation (FTC Green Guides, CMA Green Claims Code)."),
    (re.compile(r"\b(review|reviews|best seller|bestseller|most popular|rated)\b", re.I),
     "REVIEWS/POPULARITY: only real, current data with source and date; fake or undisclosed incentivised reviews are prohibited (FTC 16 CFR 465; CMA DMCC Act)."),
]


def read_csv(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def format_sections(post_type: str) -> dict[str, str]:
    name = FORMAT_FILE.get(post_type)
    if not name:
        return {}
    path = os.path.join(FORMATS_DIR, f"{name}.md")
    if not os.path.exists(path):
        return {}
    text = open(path, encoding="utf-8").read()
    sections, current = {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current:
            sections[current].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def english_variant(market: str) -> str:
    return "British English (mum, personalised, colour; £; DD Month YYYY)" if market == "uk" else \
        "American English (mom, personalized, color; $; Month D, YYYY)"


def build_brief(row: dict, topic_rows: list[dict], links: list[dict], seasonal: dict) -> str:
    slug, pt, need = row["planned_slug"], row["post_type"], row["reader_need"]
    kws = [k for k in row["keywords"].split("|") if k and k != row["primary_keyword"]]
    merged = [r["primary_keyword"] for r in sorted(topic_rows, key=lambda r: -int(float(r.get("cluster_volume") or 0)))
              if r.get("role") == "merged" and r.get("merged_into") == slug] if slug else []
    pillar = next((r for r in topic_rows if r["pillar_id"] == row["pillar_id"] and r["role"] == "pillar"), None) \
        if row["pillar_id"] else None
    sections = format_sections(pt)
    out_links = [l for l in links if l["source_slug"] == slug]
    in_links = [l for l in links if l["target_slug"] == slug and l["status"] == "update_old_post_after_target_live"]
    flags = [msg for rx, msg in FLAG_RULES if rx.search(" ".join([row["primary_keyword"], row["keywords"]])
                                                            + " " + row.get("craft", ""))]
    if row.get("craft") == "shipping" and not any(f.startswith("DELIVERY") for f in flags):
        flags.insert(0, FLAG_RULES[0][1])
    if row.get("season"):
        flags.append("SEASONAL: keep one evergreen URL and refresh it every year; update the visible date only when the content "
                     "really changes. Occasion dates differ between US and UK (compute them, do not guess). Never state order-by or delivery dates "
                     "unless operations confirms them with a date.")
    if row["market"] == "uk":
        flags.append("UK: British spelling and vocabulary; ASA may treat blog content that directly promotes the retailer's own "
                     "products as advertising, so every objective claim must be substantiable.")
    seas = seasonal.get(slug)
    L = [f"# Content brief: {row['primary_keyword']}", "",
         "## Metadata",
         f"- Planned slug: `{slug}`",
         f"- Market and English variant: {row['market'].upper() if row['market'] != 'all' else 'US (default)'} - {english_variant(row['market'])}",
         f"- Post type: {pt} (role: {row['role']}; priority bucket: {row['bucket'] or '-'})",
         f"- Pillar: {pillar['pillar_name'] + ' (' + pillar['planned_slug'] + ')' if pillar else ('no real pillar yet (research a head keyword; link to the sibling posts of the group)' if row['pillar_id'] else 'none (standalone)')}",
         f"- Reader need: {need}; cluster volume (upper bound): {int(row['cluster_volume'] or 0):,}"]
    if seas:
        L.append(f"- Season: {seas['season']} - event {seas['event_date'] or 'n/a'}; publish new by {seas['publish_new_by'] or 'n/a'}; "
                 f"refresh existing by {seas['refresh_existing_by'] or 'n/a'} (status: {seas['status']})")
    elif row.get("season"):
        L.append(f"- Season: {row['season']} - [TO FILL: run editorial-calendar to get dates]")
    L += ["", "## Reader and job to be done",
          f"The reader wants to {READER_JOB.get(need, 'get a useful answer')}.",
          "- Who exactly is searching, and what is their situation? [TO FILL after SERP review]",
          "- What would make them close the tab disappointed? [TO FILL]", "",
          "## Keywords",
          f"- Primary: {row['primary_keyword']}",
          f"- Secondary / variants (from the cluster): {', '.join(kws[:12]) if kws else '[none]'}",
          *([f"- Also covers (clusters merged into this post; answer them as sections or FAQs): {', '.join(merged[:12])}"]
            if merged else []),
          "- Use natural wording and synonyms; do not repeat the exact phrase mechanically.", "",
          "## Search intent and winning format",
          f"- Expected format: {pt}. Confirm on the real SERP (google.com for US, google.co.uk for UK), not from a Vietnam IP.",
          "- What the top results do well / what they miss (content gap): [TO FILL]",
          "- AI Overview / People Also Ask questions to answer inside this one page (do not split into separate thin pages): [TO FILL]", ""]
    if sections.get("Skeleton"):
        L += ["## Outline to follow", sections["Skeleton"], ""]
    if sections.get("Rules"):
        L += ["## Quality rules for this format", sections["Rules"], ""]
    L += ["## First-hand angle (required)",
          "Google's guidance rewards content with a point of view or experience readers cannot get from a generic summary. "
          "Fill at least one marker below with something real and checkable; never invent experience.",
          sections.get("Experience prompts", "- [TO FILL]"), "",
          "Marker syntax in the draft: `[EXPERIENCE: internal source]`, `[DATA: primary source]`, `[DATA NEEDED: what and who confirms]`.", "",
          "## Internal links (blog to blog)"]
    if out_links:
        L += ["| Anchor (adapt to the sentence, 2-8 words) | Target slug | Type | Where |", "|---|---|---|---|"]
        L += [f"| {l['anchor']} | `{l['target_slug']}` | {l['link_type']} | {l['placement']} |" for l in out_links]
    else:
        L.append("- [TO FILL: run internal-link-planner to get the link plan]")
    if in_links:
        L += ["", "After publishing, update these older posts to link here:"]
        L += [f"- `{l['source_slug']}` (anchor: {l['anchor']})" for l in in_links]
    L += ["", "## Product mentions",
          "Write the article so it is fully useful with every product mention removed. Where a product is the natural answer, "
          "leave a slot; the content team replaces it with the real link. No URLs in the draft.", ""]
    if sections.get("Product-slot guidance"):
        L += [sections["Product-slot guidance"], ""]
    else:
        L += [f"- Suggested slots: {SLOT_RANGE.get(pt, 'few, only where natural')}",
              "- Syntax: `[PRODUCT-SLOT: product idea | context: reader situation | why: why it helps this reader]`", ""]
    L += ["## Compliance flags"] + ([f"- {f}" for f in flags] if flags else ["- None triggered by the keywords; still run claims-compliance-check on the draft."])
    L += ["", "## Metadata to craft (use seo-content-vn/scripts/seo_check.py)",
          "- Title (about 50-60 characters, primary keyword first, matches H1): [TO FILL, 2-3 options]",
          "- Meta description (about 120-155 characters, concrete benefit): [TO FILL, 2-3 options]", "",
          "## Sources to cite",
          "- Prefer primary sources (.gov / .gov.uk, standards bodies, NRF/ONS-type surveys, product-team documents). [TO FILL]",
          "- Any statistic without a source stays as [DATA NEEDED: ...]; never fabricate numbers.", "",
          "## Byline and trust",
          "- Author with a real bio page; reviewer where relevant; visible published and last-updated dates.",
          "- If AI helped draft, a human editor must review facts and add original input (no scaled, low-effort publishing).", "",
          "## Definition of done",
          "- [ ] Answers the reader's question early; useful with product slots removed (`slot_check.py --strip`)",
          "- [ ] At least one real first-hand/data marker; no invented experience",
          "- [ ] `helpful_check.py` has no high findings; `claims_check.py` has no unresolved high findings",
          "- [ ] Internal links added as planned; anchors descriptive",
          "- [ ] US or UK spelling consistent; dates and currency in the right format",
          "- [ ] Placeholders resolved before publishing (`helpful_check.py --final`, `slot_check.py --final` after the content team replaced slots)", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topic-map", required=True)
    ap.add_argument("--link-plan")
    ap.add_argument("--seasonal-plan")
    ap.add_argument("--slug", help="one or more slugs, separated by commas")
    ap.add_argument("--bucket", default="A", help="priority buckets to generate briefs for, e.g. A or A,B (default A; ignored when --slug is given)")
    ap.add_argument("--role", default="pillar,cluster,standalone")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="outputs/briefs")
    args = ap.parse_args(argv)

    topic_rows = read_csv(args.topic_map)
    links = read_csv(args.link_plan) if args.link_plan else []
    seasonal = {r["planned_slug"]: r for r in read_csv(args.seasonal_plan)} if args.seasonal_plan else {}
    if args.slug:
        wanted = {s.strip() for s in args.slug.split(",")}
        chosen = [r for r in topic_rows if r["planned_slug"] in wanted]
        missing = wanted - {r["planned_slug"] for r in chosen}
        if missing:
            raise SystemExit("Slug not found: " + ", ".join(sorted(missing)))
    else:
        buckets, roles = set(args.bucket.split(",")), set(args.role.split(","))
        chosen = [r for r in topic_rows if r["role"] in roles and r["bucket"] in buckets and r["role"] != "skip"]
        chosen.sort(key=lambda r: -int(float(r["priority_score"] or 0)))
    if args.limit:
        chosen = chosen[:args.limit]
    os.makedirs(args.out, exist_ok=True)
    for r in chosen:
        with open(os.path.join(args.out, f"{r['planned_slug']}.md"), "w", encoding="utf-8") as fh:
            fh.write(build_brief(r, topic_rows, links, seasonal))
    print(f"Generated {len(chosen)} briefs -> {os.path.abspath(args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
