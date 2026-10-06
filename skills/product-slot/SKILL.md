---
name: product-slot
description: Convention and tools for mentioning products naturally in Printerval blog posts without URLs. Writers leave a PRODUCT-SLOT placeholder that describes the product, the reader's situation and the reason, and the content team replaces it with a real link. Checks slot density, placement and quality, exports a hand-off CSV, and builds a version of the post without products to test whether it is still useful. Use when the user mentions product links, slots, natural product placement, hand-off to the content team, or posts that read like ads.
---

# Product slot

The blog should lead readers to the shop, but **naturally**. Because Printerval's product and category URLs are changing and are managed by the content team, writers do not add links; they leave a **slot** that describes the exact context, and the content team picks the right product and link.

## Syntax

```
[PRODUCT-SLOT: personalized pet-portrait mug | context: gift for a dog mom | why: she sees her own dog on it every morning]
```

| Field | Required | Content |
|---|---|---|
| (first) | yes | the product type or idea, **no URL** |
| `context:` | yes | the reader's situation that the product solves |
| `why:` | yes | why it fits that situation (about the reader, at least 5 words, not a sales slogan) |
| `alt:` | no | an alternative if the first product is unavailable |

## The "natural" test (read `references/natural-integration.md`)

1. **Remove-every-slot:** delete all slots; is the post still complete and useful? (`slot_check.py --strip`)
2. **Reader problem:** does the slot solve the exact problem being discussed in that paragraph?
3. **Specific:** does `why` say something that is true only for this product and context (not usable for any product)?
4. **Position:** not in the opening; not bunched at the end; no two slots close together.
5. **Honest:** no promised price, delivery or result; any claim next to a slot still goes through `claims-compliance-check`.

## Tools

```bash
python3 skills/product-slot/scripts/slot_check.py draft.md --post-type gift-guide
python3 skills/product-slot/scripts/slot_check.py draft.md --export slots.csv     # hand-off to the content team
python3 skills/product-slot/scripts/slot_check.py draft.md --strip preview.md     # a slot-free copy to read through
python3 skills/product-slot/scripts/slot_check.py final.md --final                # before publishing: no slot may remain
```

Reference thresholds **[Convention]** (not a Google rule), by post type (maximum slots per 1,000 words; number of opening words without a slot): gift-guide 8/80, ideas-list 8/80, choose-guide 4/100, pillar-hub 6/100, how-to/explainer/copy-ideas 2/150, default 3/120. Extra warnings: a `why` that is too short or contains promotional words ("best", "perfect", "must-have"...), a URL inside a slot (error), more than half of the slots in the last 20% of the post, two slots less than 60 words apart.

## Workflow with the content team

1. The writer first writes the helpful post and leaves slots where a product is the natural answer.
2. The editor runs `slot_check.py` (no errors left) and `--export slots.csv`.
3. The content team fills the `link_added` and `link_or_note` columns for every slot, replaces the slot with a sentence plus a real link (descriptive anchor; use `rel="sponsored"` for affiliate or sponsored links), or **deletes the slot** when no suitable product exists (never force it).
4. Run `--final` (no slots left) and `claims_check.py`; re-read the whole paragraph so it flows naturally.

## For the UK market

The ASA may treat content on a seller's own website that is directly connected with the sale of goods as advertising within the CAP Code; every objective claim around a slot must be substantiated. Confirm the way to disclose with legal.
