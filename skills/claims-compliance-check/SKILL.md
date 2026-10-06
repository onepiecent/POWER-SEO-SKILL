---
name: claims-compliance-check
description: Flags risky claims in US and UK Printerval blog posts under FTC, CMA and ASA guidance (delivery times and order deadlines, reviews and popularity, environmental, health, price and offer claims, made in USA or handmade, absolute comparisons, we-tested experience claims, affiliate and sponsorship disclosure) and flags brand and IP names (franchises, artists) in a draft or a keyword list. Use when the user mentions claims, legal checks, FTC, CMA, ASA, fake reviews, delivery promises, eco-friendly wording, trademarks, IP or affiliate disclosure before publishing. Not legal advice.
---

# Claims & compliance check

A tool that **raises flags** so that a person or legal can decide; it does not conclude that something is lawful or unlawful and it is **not legal advice**. High-risk items (health, environmental, delivery, reviews, trademarks) should be confirmed by legal or the relevant team.

## Run

```bash
python3 skills/claims-compliance-check/scripts/claims_check.py draft.md --market us
python3 skills/claims-compliance-check/scripts/claims_check.py draft.md --market uk --json report.json
python3 skills/claims-compliance-check/scripts/claims_check.py --keywords outputs/keyword-map.csv --column keyword   # IP gate before writing a brief
```

The exit code is 1 when a `high` finding is still unresolved (use it as a gate before publishing).

## Rules and their basis

| Rule | Level | Basis (see `references/us-uk-claims.md`) |
|---|---|---|
| `delivery_promise` | high | FTC Mail/Internet Order Merchandise Rule: a reasonable basis for delivery times; CMA/ASA: must be substantiated |
| `review_testimonial` | high | FTC 16 CFR Part 465 (in force since 21 Oct 2024); CMA DMCC Act (since April 2025, CMA208) |
| `eco_general` | high | FTC Green Guides; CMA Green Claims Code |
| `health_claim` | high | FTC Act s.5; ASA/CAP Code |
| `made_in` | high | FTC "Made in USA" standard |
| `ip_brand` | high | USPTO/UK IPO: risk of trademark confusion; personality rights for artist names |
| `eco_specific`, `superlative_guarantee`, `price_offer`, `policy_claim`, `first_hand_claim`, `disclosure` | medium | FTC/CMA/ASA; Google (evidence of experience) |
| `handmade_claim` | low | CMA/ASA/FTC (ignore if the topic is simply DIY) |
| `uk_remit_note` | info | ASA: content on a seller's website that is directly connected with the sale of goods may fall within the CAP Code |

Every finding prints: the line, an excerpt, the matched phrases, the source, the reason, and a suggested **fix**.

## Handling a finding

1. **Fix or remove** the claim if there is no evidence. For delivery, price and reviews: replace it with `[DATA NEEDED: ... confirmed by team X, date]` or remove it.
2. **With evidence:** put the source in the post (link/date) and, if needed, have someone with authority approve it, then leave a waiver marker in the same paragraph: `[CLAIM-OK: reason; approver; date]`. A paragraph with this marker is listed under "waived" instead of being reported as an error; **never add this marker yourself** in place of the approver.
3. **First-hand experience:** keep "we tested/our team..." only when the paragraph has a real `[EXPERIENCE: source]` or `[DATA: source]`; never invent it.
4. **IP:** ask legal; mentioning a name to give honest information differs from using it to sell or promote products that carry it. Avoid putting names in titles, H2s, anchors and product descriptions until approved.

## The IP list

`assets/ip-watchlist.txt` is only a **starting list and is not exhaustive**; Printerval's legal/IP team needs to maintain the real list (one name per line; `re:` for a regex). Use the `--keywords` mode right after the clustering step to remove or review trademarked keywords before writing a brief.

## Limits

- The regexes catch surface signals: they can over-report (for example "treat stains" is not caught, but "sustainable fashion" in an opinion piece can be) and miss other phrasings. Always read the context.
- Regulations change and have exceptions by state and sector; see `references/us-uk-claims.md` for the verification level of every source.
