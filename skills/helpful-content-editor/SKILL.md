---
name: helpful-content-editor
description: Reviews, scores and edits English blog drafts (US and UK) for Printerval against people-first content criteria, covering early answers, real first-hand insight, evidence, honesty, readability, natural product mentions, no search-engine-first writing and fewer AI-sounding phrases. Use when the user sends a draft or asks to review an article, check if it is helpful, edit it to sound natural, apply E-E-A-T, or reduce AI tone.
---

# Helpful content editor

Check a draft in **two layers**: a script measures what can be measured; Claude judges the rest with `references/rubric.md`. The final result is a list of fixes ordered by impact, plus a revised draft if the user asks for one. Reply in the user's language; **edit English text directly**, in the US or UK variant, together with the `english-grammar-style` skill.

## Workflow

1. **Establish the context:** market (US/UK), `post_type` (gift-guide, ideas-list, choose-guide, how-to, explainer, copy-ideas, pillar-hub), the primary keyword, and whether there is a brief.
2. **Run the script:**
   ```bash
   python3 skills/helpful-content-editor/scripts/helpful_check.py draft.md --market us --post-type gift-guide --keyword "mother's day gifts for grandma"
   python3 skills/helpful-content-editor/scripts/helpful_check.py final.md --final     # before publishing: placeholders are errors
   ```
   The script measures: structure (one H1, H2s by section), opening length, readability (Flesch-Kincaid, long sentences, passive voice), sentences with figures but no source, "we tested" sentences without evidence, clichés and AI-sounding phrases, keyword stuffing, sales calls to action, trust signals (author, date), US/UK spelling and formats, and placeholders.
3. **Read the post as a reader** and score it with `references/rubric.md` (8 dimensions, 0-3 points each, with red flags). Claude must assess what the script cannot: whether the post has a point of view of its own, whether it covers the reader's next questions, whether it is honest, and whether the products are pushing in.
4. **Write the fix list**, at most ~7 items, ordered by impact: (1) facts and honesty, (2) answering early and matching intent, (3) original value, (4) evidence, (5) readability and structure, (6) commercial integration, (7) voice and spelling.
5. **Edit when asked:** keep the author's voice and add no facts. Add only what comes from sources the user provides; leave `[DATA NEEDED: ...]` or `[EXPERIENCE: ...]` for gaps, with the question for the right team. Re-run the script and state the score before and after.
6. **Conclude** with one of three verdicts: *ready for a human edit* / *needs revision* / *rewrite most of it*, plus the facts a person must verify (figures, names, dates).

## Never do these

- **Never invent experience, statistics, reviews or "we tested"** to make a post look authoritative. Google values real evidence of experience; inventing it is also a legal risk (FTC 16 CFR 465; CMA DMCC Act).
- **Never pad** to reach a length (there is no ideal length), never repeat keyword variants, never add fake FAQs.
- Do not add "buy now" calls to action to "increase conversions"; a helpful post leads to products through context (see `product-slot`).
- Never promise rankings. The script score is an internal heuristic, **not a Google score**.

## AI-assisted content

Google's guidance: AI is useful for research and for structuring content, but producing many pages without adding value is scaled content abuse; models can get facts wrong, so everything must be verified; consider saying how the content was created. So for an AI draft: (a) verify every figure, name and date, (b) add at least one real original contribution, (c) have a person edit it before publishing, (d) never publish in bulk without review. The Quality Rater Guidelines treat main content produced with automated tools and little effort, originality or value as the lowest quality level.

## Related documents

- `references/rubric.md`: the 8 dimensions, questions, scoring scale, red flags and how to fix them.
- `references/voice-and-style.md`: voice for a gifting blog, US vs UK, plain language, replacements for clichés.
