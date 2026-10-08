---
name: topic-map
description: Builds a pillar and cluster map for the Printerval blog from clusters.csv (the output of keyword-clustering). Chooses pillars by occasion, interest, recipient, know-how (sizing, washing, printing) and inspiration (slogans, captions), splits a one-topic export into theme pillars (dates, history, activities, quotes), merges small clusters into the closest post, checks an SEO's own pillars and posts against the same rules, chooses hubs by the traffic the site can win, ranks posts A, B or C, shows content gaps, and removes pure shopping keywords from the blog plan. Use when the user mentions pillars, clusters, a topic map, a blog content plan, or which posts to write first.
---

# Topic map: pillar/cluster

Takes `clusters.csv` and produces `topic-map.csv` (for machines) and `topic-map.md` (for people). Each **cluster = one post**; a **pillar** post is the hub page for a topic; a **cluster** post is a detailed post that belongs to a pillar. Pillar/cluster and "topical authority" are an industry **[Convention]**, not Google concepts: do not promise ranking results just because this structure exists.

## Run

```bash
python3 skills/topic-map/scripts/topic_map.py outputs/clusters.csv --out outputs
python3 skills/topic-map/scripts/topic_map.py outputs/clusters.csv --priority occasion,interest,recipient,craft --min-clusters 3
python3 skills/topic-map/scripts/topic_map.py outputs/clusters.csv --max-pillar-size 30 --min-post-volume 300 --keep-volume 2000
python3 skills/topic-map/scripts/topic_map.py outputs/clusters.csv --seo-min-post-volume 150   # an audited SEO grouping
```

## How pillars are chosen (explainable)

Clusters are assigned stage by stage in priority order (default `occasion,interest,recipient,craft`, then `inspiration`, then `product`). At each stage, clusters with the same facet value (for example `occasion=mothers-day`) form a pillar **if there are at least `--min-clusters` of them** (default 3); clusters not taken fall through to the next stage. A cluster that no stage takes is `standalone` (with a `parent_hint` when a related pillar exists).

- Know-how posts (how-to, solve, info about washing, sizing, printing) always go to a `craft` pillar, never to an audience pillar.
- Very broad recipients ("her", "him") do not form pillars.
- **The SEO's own pillars come first.** When `clusters.csv` comes from a grouped file (`--prior`, e.g. the SEO's sheet or the team's earlier final plan), a group whose *Category Kind* / *Kind* is `Pillar` is a hub, and every group whose *Thuộc Pillar* names that hub's main keyword is its post. A *Thuộc Pillar* that names no blog cluster of this run (e.g. "No real pillar yet ...") and every group without one go through the stages below. With `--prior-mode keep` these pillars stay exactly as the file set them. With an **audited** grouping (the default, `grouping_basis` `prior:audited`) the structure is checked too, each change a row of `seo-audit-topic.csv` (sheet SEO Audit of the final plan):
  - `pillar_fit`: a post that shares no subject word with its pillar but does with another SEO pillar moves there.
  - `pillar_changed`: a group at least as broad as the SEO's pillar (its subject words are a subset of the pillar's) that wins >= 1.5x the pillar's **winnable volume** (volume x fit of its KD against the site's reach, keyword-clustering) becomes the hub: the pillar should target the query the site can rank for, and its posts pass their authority to it.
  - `same_subject`: two groups that ask the same thing once angle words (step by step, professionally, like a pro, ideas, tips...) are set aside become one post (`... christmas tree step by step` and `... christmas tree professionally`); a group with the pillar's own subject joins the pillar.
  - `section`: a group with less than `--seo-min-post-volume` (100) searches a month is too little demand for a page of its own; it becomes a section (and its keywords secondary keywords) of the post whose subject words it narrows (`sparse christmas tree` -> the tree guide), else of the pillar [Convention].
  - `kept_apart`: two clusters that keyword-clustering says are different posts (`clusters.csv` `keep_apart_from`: their SERPs share fewer than 4 top-10 URLs, or a `keep_apart` decision) are never merged as the same subject, and a section never goes into a post it must stay apart from (`easy trio halloween costumes`, 2 of 7 URLs shared with `trio halloween costumes`, stays a post). A raw export's sub-topic merges honour the column too [Google: the live SERP].
  Change any of it with decisions (`set_pillar`, `promote_pillar`, `demote_pillar`, `restore_backlog`, `drop_post`).
- The hub of an **audience pillar** (occasion, recipient, interest) must cover the whole group: a cluster that names a narrower product, recipient or interest (`christmas shirt ideas`, `christmas gifts for mom` in the Christmas group) is never its hub, neither chosen nor promoted.
- The pillar page is the "list" cluster (inspire/choose) with the largest volume and the fewest extra facets; if there is none, **no virtual pillar is invented** (a made-up slug with no keyword or volume behind it only produces a thin hub and dead links). Instead: (a) if the group's strongest cluster has >= `--promote-min-volume` (50) and >= `--promote-min-share` (15%) of the group's volume, it is **promoted to the real pillar** (e.g. `how to make custom mugs`, 110 of ~500); (b) otherwise the group has **no pillar row at all**: its posts get the note "No real pillar yet: research a head keyword" (the final plan shows it in the pillar column), link to each other, and the SEO researches a head keyword before a hub is written. Promotion thresholds are internal heuristics **[Convention]**. If a group is small, also ask whether it needs its own group or just one how-to post.
- `blog_fit=low` clusters (shopping intent) become `role=skip`; no blog post is written.
- Extra stage: `--priority category,occasion` uses the custom groups (`--categories` in the clustering step).

## Big topics: theme pillars and merged posts

A one-topic export (all "thanksgiving") would otherwise give one pillar with thousands of clusters. So:

1. **Split by theme.** A pillar with more than `--max-pillar-size` clusters (default 30) becomes one pillar per theme: *Thanksgiving Dates & Calendar*, *History & Origins*, *Meaning & Symbols*, *Facts & Trivia*, *Traditions, Activities & Games*, *Quotes, Messages & Prayers*, *Around the World*... A theme becomes a pillar with at least `--min-clusters` clusters and enough volume (>= 500 and >= 2% of the topic's volume outside its biggest theme); a smaller theme joins its fallback (facts -> meaning, food/events/printables -> activities, images/humor -> messages); clusters with no theme first look for a theme pillar that holds a cluster asking the same thing (`thanksgiving names` -> the pillar of `another name for thanksgiving`); the rest go to the **backlog** (`role=backlog`, not planned), or become standalone posts when they are big. At most `--max-sub-pillars` (10) theme pillars.
2. **The hub of a theme pillar** names no narrower audience or product than the pillar (`christmas gift ideas`, not `christmas gifts for mom`), then is its broadest cluster (empty core: `history of thanksgiving`, `when is thanksgiving`), then the one the site can win most traffic with (**winnable volume**, not raw volume: a keyword the blog cannot rank for brings nothing). A promoted hub likewise has the fewest extra facets first.
3. **Keep the strongest sub-topics, merge the rest.** There is **no cap on the number of posts per pillar** by default (`--max-posts 0`; set `--max-posts N` only if you want one): the thresholds below alone decide, so a pillar with 99 clusters keeps every sub-topic that earns a post. A pillar of up to `--keep-all-up-to` (12) clusters keeps every cluster. In a bigger pillar, posts are chosen by **sub-topic**, not cluster by cluster: every core and every word of a core is a candidate (`games` is shared by `thanksgiving games for adults`, `... for the table`, `... youth group`), scored by the volume it would own. Greedily, the candidate that owns the most is kept while it owns >= `--min-post-volume` (300), >= `--min-post-share` (2%) of the pillar's volume outside the hub and >= 10% of the strongest sub-topic; a sub-topic owning >= `--keep-volume` (2,000) is always kept (so `thanksgiving story for kindergarten` is not lost next to `the first thanksgiving`). A narrower sub-topic of a kept post (`first` -> `first + food`) needs >= 10% of that post's volume; one that only adds who or when (`books` -> `books for kids`, `travel` -> `travel thanksgiving weekend`) stays a section of it. The post is named after the sub-topic's strongest broad cluster (its main keyword's volume and its cluster's total both count, then the most natural name). Every other cluster gets `role=merged` and `merged_into=<slug>`; its keywords become secondary keywords and sections of that post, which is how one post covers many phrasings (and avoids thin pages). Two theme pillars never keep the same post: `why do we celebrate thanksgiving on thursday` (meaning) joins `is thanksgiving always on a thursday` (dates). `--target-posts N` can also cap the plan at about N posts.
4. **Theme gaps.** When a topic was split, `topic-map.md` names the themes the file barely covers but the blog needs (gifts and shirts, sayings and quotes, decor): export those seed keywords before planning them.

**Sub-hubs.** Within a pillar, a kept post whose subject is one word (`how to decorate a christmas tree`: {tree}) heads the other kept posts about that word when there are at least 3 of them (`... with ribbon`, `white ...`, `pink ...`): `parent_post` in `topic-map.csv` names it and the note says "sub-hub". The pillar then links to the sub-hub and the sub-hub to its posts (internal-link-planner), instead of one pillar linking to every post.

**Priority score** = `cluster_winnable` (winnable volume from keyword-clustering) x blog-fit weight (1 / 0.6 / 0.15); with an older `clusters.csv`: `cluster_volume` x weight x (0.5 + 1 - KD/100). Bucket **A** = top 20%, **B** up to 50%, the rest **C**. This is a heuristic for ordering work (value x achievability matrix), not a traffic forecast. `topic-map.csv` also carries `winnable` and `main_kd_fit` (easy / stretch / hard / unknown for the site) for the link planner.

## Reading and checking the output

1. Open `topic-map.md`: every pillar has a table of clusters, post types, priority and a **Content gaps** line (missing gift guides by recipient, missing slogans/captions/card messages, missing how-tos...). That is a list of extra keyword research to do, not an order to write posts.
2. Check these points by hand and tell the user:
   - Pillars that should be merged or split (for example two similar interest pillars). Big topics are split by theme automatically; check that each theme pillar makes sense and that its hub is a real hub.
   - The `+ merged clusters` column: a post that absorbed many clusters needs sections for them (the brief lists them under "Also covers").
   - `info` clusters with large volume that are only a short answer: they should be a section of a pillar rather than a post of their own.
   - Clusters at risk of **cannibalization** (two clusters with nearly the same intent): see `merge-candidates.csv` from the clustering step.
   - Seasonal clusters (`season`): hand them to `editorial-calendar`.
3. Hand over to the user: the number of pillars, clusters, merged, backlog, standalone and skipped items, the top bucket-A posts, the gaps, and the decisions they need to make.
4. For the content team's sheet, run `printerval-blog-seo/scripts/export_plan.py` (after `internal-link-planner`).

## Next steps

`editorial-calendar` (publish dates for seasonal posts) -> `internal-link-planner` (links between posts) -> `content-brief` (briefs for bucket A).

## Limits

- The slug (`planned_slug`) is a planned slug generated from the keyword, **not a real URL**; Printerval's URLs and sitemap are being optimized separately.
- Facets come from regexes in the taxonomy: a niche that is not in the taxonomy becomes standalone or unclassified (see `keyword-clustering/references/taxonomy-guide.md`).
- With little data (a few dozen clusters) it is normal for few pillars to reach the 3-cluster threshold; lower it with `--min-clusters 2` when needed, but do not create thin pillars just to have a structure.

Related document: `references/pillar-types.md` (pillar types, names, expected coverage, how to write a hub page).
