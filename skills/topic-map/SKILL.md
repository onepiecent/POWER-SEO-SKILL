---
name: topic-map
description: Builds a pillar and cluster map for the Printerval blog from clusters.csv (the output of keyword-clustering). Chooses pillars by occasion, interest, recipient, know-how (sizing, washing, printing) and inspiration (slogans, captions), ranks posts A, B or C, shows content gaps, and removes pure shopping keywords from the blog plan. Use when the user mentions pillars, clusters, a topic map, a blog content plan, or which posts to write first.
---

# Topic map: pillar/cluster

Takes `clusters.csv` and produces `topic-map.csv` (for machines) and `topic-map.md` (for people). Each **cluster = one post**; a **pillar** post is the hub page for a topic; a **cluster** post is a detailed post that belongs to a pillar. Pillar/cluster and "topical authority" are an industry **[Convention]**, not Google concepts: do not promise ranking results just because this structure exists.

## Run

```bash
python3 skills/topic-map/scripts/topic_map.py outputs/clusters.csv --out outputs
python3 skills/topic-map/scripts/topic_map.py outputs/clusters.csv --priority occasion,interest,recipient,craft --min-clusters 3
```

## How pillars are chosen (explainable)

Clusters are assigned stage by stage in priority order (default `occasion,interest,recipient,craft`, then `inspiration`, then `product`). At each stage, clusters with the same facet value (for example `occasion=mothers-day`) form a pillar **if there are at least `--min-clusters` of them** (default 3); clusters not taken fall through to the next stage. A cluster that no stage takes is `standalone` (with a `parent_hint` when a related pillar exists).

- Know-how posts (how-to, solve, info about washing, sizing, printing) always go to a `craft` pillar, never to an audience pillar.
- Very broad recipients ("her", "him") do not form pillars.
- The pillar page is the "list" cluster (inspire/choose) with the largest volume and the fewest extra facets; if there is none, a **virtual pillar** is created (a topic with no head post yet: research a head keyword, then write it as a hub).
- `blog_fit=low` clusters (shopping intent) become `role=skip`; no blog post is written.
- Extra stage: `--priority category,occasion` uses the custom groups (`--categories` in the clustering step).

**Priority score** = `cluster_volume` x blog-fit weight (1 / 0.6 / 0.15) x (0.5 + achievability), achievability = 1 - KD/100 (missing KD = 0.5). Bucket **A** = top 20%, **B** up to 50%, the rest **C**. This is a heuristic for ordering work (value x achievability matrix), not a traffic forecast.

## Reading and checking the output

1. Open `topic-map.md`: every pillar has a table of clusters, post types, priority and a **Content gaps** line (missing gift guides by recipient, missing slogans/captions/card messages, missing how-tos...). That is a list of extra keyword research to do, not an order to write posts.
2. Check these points by hand and tell the user:
   - Pillars that should be merged or split (for example two similar interest pillars; a pillar with more than 30 clusters needs sub-hubs).
   - `info` clusters with large volume that are only a short answer: they should be a section of a pillar rather than a post of their own.
   - Clusters at risk of **cannibalization** (two clusters with nearly the same intent): see `merge-candidates.csv` from the clustering step.
   - Seasonal clusters (`season`): hand them to `editorial-calendar`.
3. Hand over to the user: the number of pillars, clusters, standalone and skipped items, the top bucket-A posts, the gaps, and the decisions they need to make.

## Next steps

`editorial-calendar` (publish dates for seasonal posts) -> `internal-link-planner` (links between posts) -> `content-brief` (briefs for bucket A).

## Limits

- The slug (`planned_slug`) is a planned slug generated from the keyword, **not a real URL**; Printerval's URLs and sitemap are being optimized separately.
- Facets come from regexes in the taxonomy: a niche that is not in the taxonomy becomes standalone or unclassified (see `keyword-clustering/references/taxonomy-guide.md`).
- With little data (a few dozen clusters) it is normal for few pillars to reach the 3-cluster threshold; lower it with `--min-clusters 2` when needed, but do not create thin pillars just to have a structure.

Related document: `references/pillar-types.md` (pillar types, names, expected coverage, how to write a hub page).
