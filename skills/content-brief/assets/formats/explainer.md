# Format: explainer

Use when: reader_need = info ("what is DTG printing", "when is Mother's Day", "what does ... mean").
Reader job: get a correct answer immediately, then understand it well enough to act.

## Skeleton
- H1: the question or term in plain words.
- Direct answer in the first two sentences (definition, date, number).
- H2: How it works / what it means (plain language, examples)
- H2: How it compares with alternatives (table when useful)
- H2: What it means for you (practical implications for the reader's decision)
- H2: FAQs
- Byline, "Last updated", sources.

## Rules
- Date questions: compute the date with weekday for each market (US and UK can differ, e.g. Mother's Day vs Mothering Sunday); never guess. Use editorial-calendar/scripts/occasion_calendar.py.
- Define terms once, simply. Avoid jargon without explanation.
- If the topic is a short answer, keep the page short; it may belong as a section of a pillar page instead.

## Experience prompts
- What do customers misunderstand about this? (support patterns)
- Where does the production team see this matter in practice? (named role, documented)

## Product-slot guidance
- Usually zero or one slot, near the "what it means for you" section.
- Slot syntax: [PRODUCT-SLOT: product idea | context: reader situation | why: why it helps this reader]
