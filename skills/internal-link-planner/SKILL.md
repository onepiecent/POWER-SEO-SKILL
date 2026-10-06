---
name: internal-link-planner
description: Plans internal links between Printerval blog posts (pillar to cluster, posts in the same cluster, cross links, links back from older posts) from topic-map.csv, suggests descriptive anchors, flags orphan posts and dead ends, and audits an existing link export (Screaming Frog or Ahrefs with source, target and anchor columns). Use when the user mentions internal links, anchor text, orphan pages or linking older posts to new ones. Does not plan links to product or category pages.
---

# Internal link planner (blog <-> blog)

Scope: **links between blog posts only**. Links to products are added by the content team through `[PRODUCT-SLOT]` (the `product-slot` skill). Printerval's URLs and sitemap are changing, so the plan uses **planned slugs** (`planned_slug`), not real URLs.

## Two modes

```bash
# 1. Plan from the topic map
python3 skills/internal-link-planner/scripts/link_plan.py plan outputs/topic-map.csv --out outputs
python3 skills/internal-link-planner/scripts/link_plan.py plan outputs/topic-map.csv --published published.csv --out outputs

# 2. Audit an existing link file (columns source,target,anchor; from/to/anchor text/link text are also accepted)
python3 skills/internal-link-planner/scripts/link_plan.py audit links.csv --topic-map outputs/topic-map.csv --out outputs
```

Only planned posts get links (`role` pillar, cluster, standalone); clusters merged into another post (`role=merged`) and the backlog have no page of their own. Anchors come from the target's own keywords and never contain a year (a seasonal post keeps one URL for years). The final plan for the content team (`printerval-blog-seo/scripts/export_plan.py`) turns this file into the "Internal Link (Anchor || URL)" and "Related Post (Anchor || URL)" columns.

`published.csv`: one `slug` (or `url`) column listing the published posts. With this file, `status` shows which links **go into a new draft**, which ones **require updating an old post once the target is live**, and which already exist.

## Rules (with evidence levels)

- Links must be crawlable `<a href>` elements; anchors **descriptive, short and relevant to the target page**; every important page needs at least one link pointing to it; links sit in a context that helps the reader. **[Google]** (SEO link best practices)
- There is no "ideal" number of links; too many links dilute each one. **[Google]**
- Pillar <-> every cluster (a child post links up to the pillar with an anchor that contains the pillar topic; the pillar links down to each cluster); posts in the same cluster cross-link when relevant; at most 3 siblings per post and 1 cross-pillar link. **[Convention]**
- Reference density 3-5 contextual links per 1,000 words; the 1-2 most important links in the first half of the post; one link per target URL per post; anchors of 2-8 words, varied but **never the same anchor for two different URLs**. **[Convention]**
- Zyppy research (23 million links, **correlation, not causation**): a page receiving about 40-44 inbound links gets far more clicks than one with 0-4; beyond about 45-50 the effect reverses; orphan pages get almost no organic traffic. The script only uses the ~50 threshold to **flag for review**. **[Research]**
- When publishing a new post: update 2-5 older posts on the same topic so they link to it (`backlink_old_post`). **[Convention]**

## Workflow

1. Run `plan`; read `link-summary.md`: links by type, orphan posts and dead ends, and the **"not resolvable"** section.
2. **Never force links between unrelated posts.** Posts that have no same-topic post to link to naturally are listed separately: that is a content gap (add a post on the same topic) or a decision for the editor.
3. When writing a post, give the writer the table `anchor -> target slug -> position -> reason` for that post (already included in `content-brief`). The anchors in the CSV are only **suggestions**: rewrite them to fit the sentence, in the market's spelling (mum/mom, personalised/personalized).
4. Once real URLs exist (when the sitemap is stable), map `planned_slug` -> URL. If the real slug differs from the planned one (redirect, rename), build a mapping table before running `audit`.
5. Run `audit` regularly (quarterly for a small site) with the crawler's link export; fix by severity: `high` (orphan posts, clusters that do not link up to the pillar, pillars that do not link down to clusters, generic anchors such as "click here"), `medium` (dead ends, the same anchor used for several targets, empty anchors), `low` (anchors that are too short or too long, duplicate links, high density).

## How `audit` matches posts

It matches by the **last path segment** (dropping `.html/.php`, parameters and capital letters), so a URL that was redirected to a different slug will not match. Links to pages outside the blog (products, categories) are still counted as a "node" and may be reported as orphans: filter the export down to blog URLs before auditing.

## Limits

- The plan is based on keyword facets and vocabulary and has not read the real post content; once a post is written, Claude should read it and suggest link positions semantically.
- Without crawl data it cannot know which links already exist unless you provide `published.csv` or run `audit`.
