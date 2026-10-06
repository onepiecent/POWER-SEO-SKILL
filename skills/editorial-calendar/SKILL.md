---
name: editorial-calendar
description: Computes US and UK holiday dates by rule (US Mother's Day versus UK Mothering Sunday, Father's Day, Thanksgiving, Black Friday, Easter, Halloween, Bonfire Night) and plans publish and refresh deadlines for seasonal blog posts from the topic map. Use when the user mentions a content calendar, seasonal posts, when to publish Mother's Day or Christmas content, or US and UK holiday dates.
---

# Seasonal editorial calendar (US/UK)

## Run

```bash
python3 skills/editorial-calendar/scripts/occasion_calendar.py --year 2027 --market both --out outputs
python3 skills/editorial-calendar/scripts/occasion_calendar.py --topic-map outputs/topic-map.csv --out outputs    # also writes seasonal-plan.csv
python3 skills/editorial-calendar/scripts/occasion_calendar.py --today 2026-10-06 --lead-new 16 --lead-refresh 8 ...
```

Output: `occasion-calendar.csv/.md` (every occasion, both markets) and `seasonal-plan.csv` (every post with a `season` in the topic map: the next event date, `publish_new_by`, `refresh_existing_by`, `days_to_publish_by`, `status`).

## What to remember

1. **Dates are COMPUTED by rule, not taken from search results.** During the research a search engine returned wrong dates for UK Mothering Sunday and Father's Day; the script has tests that check the dates against the real calendar (see `tests/`). Never type a date into a post by hand.
2. **The US and the UK differ:** US Mother's Day = the second Sunday of May; UK Mothering Sunday = three weeks before Easter (March or April). Father's Day follows the same rule in both (the third Sunday of June). Thanksgiving and the Fourth of July are US only; Bonfire Night is UK only. Each market is a separate row, and a separate post when needed.
3. **Lead time is a convention, not a Google rule.** The defaults are 12 weeks for a new post and 6 weeks for refreshing an old one (Google does not publish indexing or ranking times). Calibrate with real seasonality: Search Console (weekly impressions of last year's seasonal posts) and Google Trends. The "graduation" and "back to school" windows are only **approximate**.
4. **One URL per season, refreshed every year.** Keep the occasion pillar/guide, update the content, and change the visible date only when the content really changes (Google advises against artificially freshened dates; the visible date should match the structured data). Do not create `...-2027`.
5. **Do not promise delivery.** Seasonal posts love to say "order before date X". Order and delivery deadlines come only from operations, with a confirmation date (`[DATA NEEDED: ...]`), because the FTC Mail/Internet Order Merchandise rule requires a reasonable basis for any stated delivery time and the CMA/ASA require claims to be substantiated. The `notes` column carries this reminder for Valentine's Day, Mother's/Father's Day and Christmas.
6. **Demand context (US):** the 2026 NRF surveys (through search summaries; re-check the original page before quoting) show Mother's Day, Valentine's Day and Halloween spending at record levels, with online the top shopping destination for several occasions. That is a reason to prioritise seasonal posts, not evidence about rankings.

## Reading `seasonal-plan.csv`

| `status` | Meaning | What to do |
|---|---|---|
| `upcoming` | the deadline for a new post is more than 14 days away | schedule it by `publish_new_by` |
| `due_soon` | the deadline is within 14 days | prioritise now |
| `overdue` | the deadline for a new post has passed but the event has not arrived | publish as soon as possible **or** refresh the existing post (`refresh_existing_by`) and put the effort into bucket-A posts |
| `no_calendar_rule` | the `season` has no date rule yet | add it to `OCCASIONS` in the script or set a date by hand |

An event that has already passed this year moves automatically to its next occurrence (next year). To add an occasion: edit `OCCASIONS` (rules `fixed`, `nth`, `easter`, `after`, `window`) and add a test that checks the real date.

## Not in the script

UK bank holidays (they have complicated "substitute day" rules): use https://www.gov.uk/bank-holidays. Remembrance and other sensitive occasions are not part of a gifting calendar. See the per-occasion notes in `references/occasions.md`.
