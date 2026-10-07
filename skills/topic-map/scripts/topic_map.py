#!/usr/bin/env python3
"""Build a pillar/cluster map from clusters.csv (the output of keyword-clustering). Standard library only.

Output: <out>/topic-map.csv  and  <out>/topic-map.md

Main rules:
  * Each cluster belongs to exactly ONE pillar, chosen by facet priority (--priority, default
    occasion,interest,recipient,craft). The remaining facets are used for cross links (internal-link-planner).
  * A pillar needs >= --min-clusters clusters; with fewer, the clusters stand alone (standalone) and only get a suggested parent pillar.
  * A pillar with more than --max-pillar-size clusters (typical of a one-topic export such as 'thanksgiving') is split
    into one pillar per theme (dates, history, meaning, activities, messages...). A theme that is too small joins its
    fallback theme (facts -> meaning, food -> activities...); clusters left without a pillar go to the backlog.
  * A pillar with more than --max-posts clusters keeps its hub and its strongest SUB-TOPICS: words that many clusters
    share ('games' in 'thanksgiving games for adults', '... for the table', '... youth group') are scored by the volume
    they would own, so a long tail that adds up becomes one post. A sub-topic needs >= --min-post-volume and
    >= --min-post-share of the pillar's volume outside the hub; a narrower sub-topic of a kept post ('first' ->
    'first + food') needs >= 10% of that post's volume, and an audience-only narrowing ('books' -> 'books for kids')
    stays a section of it. Every other cluster is merged into the closest kept post (role 'merged', column
    merged_into), so its keywords become secondary keywords of it.
  * Long-tail clusters left without a theme pillar join a kept post that asks the same thing ('thanksgiving names'
    -> 'another name for thanksgiving'); only those that match nothing go to the backlog.
  * Clusters with blog_fit = low (pure shopping intent) are marked skip and left out of the blog map.
  * Priority score = cluster_volume x blog_fit weight x (0.5 + achievability), achievability = 1 - KD/100
    (missing KD -> 0.5). This is a ranking heuristic, not a Google metric.
  * --decisions FILE (the shared decisions contract): set_pillar, promote_pillar, demote_pillar, restore_backlog and
    drop_post are applied to the plan before slugs are assigned; every one is logged in decisions-log-topic.csv and
    the applied ones are listed in the decision_ids column of topic-map.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
import zipfile
from collections import defaultdict
from xml.etree import ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
TAXONOMY_CANDIDATES = [
    os.path.join(HERE, "..", "assets", "taxonomy.json"),
    os.path.join(HERE, "..", "..", "keyword-clustering", "assets", "taxonomy.json"),
]
FIT_WEIGHT = {"high": 1.0, "medium": 0.6, "low": 0.15}
GENERIC_RECIPIENTS = {"her", "him"}  # too broad to be a pillar
KNOWHOW_NEEDS = {"how_to", "solve", "info"}
LIST_NEEDS = {"inspire", "choose"}
EXPECTED_BY_TYPE = {
    "occasion": ["list", "copy_ideas", "info"],
    "interest": ["list", "copy_ideas", "how_to|solve"],
    "recipient": ["list", "copy_ideas"],
    "craft": ["how_to|solve", "info|choose"],
    "product": ["list", "how_to|solve"],
}
GAP_HINT = {
    "list": "gift guide by recipient or budget",
    "copy_ideas": "slogans / quotes / captions / card messages",
    "info": "what is / when is / meaning / history",
    "how_to": "how to personalize / design / care for",
    "solve": "problem solving: washing, shrinking, choosing a size",
    "choose": "best X / X vs Y / how to choose",
}


def load_taxonomy(path: str | None) -> dict | None:
    for cand in ([path] if path else TAXONOMY_CANDIDATES):
        if cand and os.path.exists(cand):
            with open(cand, encoding="utf-8") as fh:
                return json.load(fh)
    return None


def prettify(key: str) -> str:
    return " ".join(w.capitalize() for w in key.replace("-", " ").split())


def pillar_title(ptype: str, key: str, market: str, tax: dict | None) -> str:
    if ptype == "product" and tax and key in tax["facets"]["product"]["values"]:
        return f"{tax['facets']['product']['values'][key]['label']}: Ideas & Guides"
    if ptype == "product":
        return f"{prettify(key)}: Ideas & Guides"
    if tax and ptype in tax["facets"] and key in tax["facets"][ptype].get("values", {}):
        spec = tax["facets"][ptype]["values"][key]
        label = spec.get("label_uk") if market == "uk" and spec.get("label_uk") else spec["label"]
        tpl = tax["facets"][ptype].get("title_template", "{label}")
        return tpl.format(label=label)
    if ptype == "occasion":
        return f"{prettify(key)} Gift Ideas"
    if ptype in ("interest", "recipient"):
        return f"Gift Ideas for {prettify(key)}"
    if ptype == "craft":
        return f"{prettify(key)} Guide"
    if ptype == "inspiration":
        return "Slogans, Quotes & Caption Ideas"
    return prettify(key)


def slugify(text: str) -> str:
    s = text.lower().replace("’", "").replace("'", "")
    s = re.sub(r"\b(19|20)\d\d\b", " ", s)  # evergreen URLs: one URL per season, refreshed every year
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > 60:
        s = s[:60].rsplit("-", 1)[0]
    return s


def to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def stage_key(row: dict, stage: str) -> str:
    """Pillar key of a cluster at one priority 'stage'; empty means the cluster does not belong to this stage."""
    need = row["reader_need"]
    if stage in ("occasion", "interest", "recipient") and row.get("craft") and need in KNOWHOW_NEEDS:
        return ""  # know-how posts (washing, sizing, printing) belong to the craft pillar, not to an audience pillar
    if stage == "recipient" and row.get("recipient") in GENERIC_RECIPIENTS:
        return ""
    if stage == "craft":
        if row.get("craft"):
            return row["craft"]
        return (row.get("product") or "") if need in ("how_to", "solve") else ""
    if stage == "inspiration":
        return "copy-ideas" if need == "copy_ideas" else ""
    return row.get(stage) or ""


def stage_type(stage: str) -> str:
    return stage


def assign_groups(live: list[dict], priority: list[str], min_clusters: int):
    """Assign clusters to pillars stage by stage: a stage that has >= min_clusters clusters with the same key becomes a pillar,
    the remaining clusters fall through to the next stage. A cluster that no stage takes stands alone."""
    stages = priority + [s for s in ("inspiration", "product") if s not in priority]
    groups: dict[tuple, list[dict]] = {}
    remaining = list(live)
    for stage in stages:
        buckets: dict[tuple, list[dict]] = defaultdict(list)
        for r in remaining:
            key = stage_key(r, stage)
            if key:
                buckets[(r["market"], key)].append(r)
        taken = set()
        for (market, key), members in buckets.items():
            if len(members) >= min_clusters:
                groups[(market, stage_type(stage), key)] = members
                taken.update(id(m) for m in members)
        remaining = [r for r in remaining if id(r) not in taken]
    return groups, remaining


def post_type(row: dict, is_pillar: bool) -> str:
    if is_pillar:
        return "pillar-hub"
    need = row["reader_need"]
    # 'thanksgiving trivia' or 'thanksgiving traditions' are idea lists, not gift guides: only the gifts theme (or no
    # theme) of an occasion / recipient / interest is a gift guide
    has_gift_facet = any(row.get(f) for f in ("occasion", "recipient", "interest")) and row.get("theme", "") in ("", "gifts")
    if need == "inspire":
        return "gift-guide" if has_gift_facet else "ideas-list"
    if need == "choose":
        return "gift-guide" if has_gift_facet and "gift" in row["cluster_name"].lower() else "choose-guide"
    return {"how_to": "how-to", "solve": "how-to", "copy_ideas": "copy-ideas",
            "info": "explainer", "shop": "skip"}.get(need, "explainer")


def priority_score(row: dict) -> int:
    kd = to_int(row.get("seed_kd"), -1)
    achievable = 0.5 if kd < 0 else max(0.0, 1 - kd / 100)
    return round(to_int(row["cluster_volume"]) * FIT_WEIGHT.get(row["blog_fit"], 0.6) * (0.5 + achievable))


def narrower_facets(r: dict, own_facet: str) -> int:
    """How many facets narrower than its audience group (occasion, recipient, interest) a cluster names: 'christmas
    shirt ideas' in the Christmas group names a product (1), 'christmas gifts for mom' a recipient (1). The hub of an
    audience pillar must cover the whole group, so only a cluster with 0 can be it; craft, product, category and
    inspiration groups are keyed by what their clusters share and keep their own rule."""
    if own_facet not in ("occasion", "recipient", "interest"):
        return 0
    return sum(1 for f in ("occasion", "recipient", "interest", "product", "craft") if f != own_facet and r.get(f))


def choose_pillar_cluster(rows: list[dict], own_facet: str) -> dict | None:
    eligible = [r for r in rows if r["reader_need"] in LIST_NEEDS and r["blog_fit"] == "high"
                and not narrower_facets(r, own_facet)]
    if not eligible:
        return None

    def specificity(r):
        return sum(1 for f in ("occasion", "recipient", "interest", "product", "craft")
                   if f != own_facet and r.get(f))
    return sorted(eligible, key=lambda r: (specificity(r), -to_int(r["cluster_volume"])))[0]


SEO_PILLAR_ROLES = ("pillar", "pillar-hub", "pillar hub", "hub")


def seo_pillars(live: list[dict]) -> tuple[list, dict, list[dict]]:
    """The pillars the SEO's grouped file already set (clusters.csv prior_role / prior_pillar, from the plan's Category
    Kind and Thuộc Pillar): a group whose Category Kind is 'Pillar' is a hub, and the groups whose Thuộc Pillar names
    a hub's main keyword are its posts. They stay as the file set them, with no merging; a Thuộc Pillar that names no
    blog cluster of this run (e.g. 'No real pillar yet ...') and every group without one go through the engine.
    Returns ([(group key, (members, theme))], {group key: hub}, the clusters left to the engine)."""
    by_main: dict[tuple, dict] = {}
    for r in live:
        by_main.setdefault((r["market"], decision_key(r["cluster_name"])), r)
    hubs = {id(r): r for r in live
            if r.get("prior_group") and (r.get("prior_role") or "").strip().lower() in SEO_PILLAR_ROLES}
    posts: dict[int, list[dict]] = defaultdict(list)
    for r in live:
        hub = by_main.get((r["market"], decision_key(r.get("prior_pillar") or "")))
        if hub is not None and hub is not r and r.get("prior_group"):
            hubs[id(hub)] = hub  # named as the pillar of another group: a hub even without Category Kind
            posts[id(hub)].append(r)
    items, hub_of, taken = [], {}, set()
    for h in hubs.values():
        members = [h] + [m for m in posts[id(h)] if id(m) not in hubs and id(m) not in taken]
        ptype = next((f for f in ("occasion", "interest", "recipient", "craft", "product") if h.get(f)), "topic")
        key = (h["market"], ptype, "seo-" + slugify(h["cluster_name"]))
        items.append((key, (members, "")))
        hub_of[key] = h
        taken.update(id(m) for m in members)
    return items, hub_of, [r for r in live if id(r) not in taken]


def has_need(needs: set[str], spec: str) -> bool:
    for alt in spec.split("|"):
        if alt == "list":
            if needs & LIST_NEEDS:
                return True
        elif alt in needs:
            return True
    return False


def volume(r: dict) -> int:
    return to_int(r["cluster_volume"])


def core_of(r: dict) -> frozenset:
    return frozenset((r.get("core") or "").split())


def theme_specs(tax: dict | None) -> tuple[dict, list[str]]:
    if not tax or "theme" not in tax["facets"]:
        return {}, []
    values = tax["facets"]["theme"]["values"]
    return values, list(values)


def theme_pillar_title(ptype: str, key: str, theme: str, market: str, tax: dict | None) -> str:
    specs, _ = theme_specs(tax)
    label = specs.get(theme, {}).get("label", prettify(theme))
    if theme == "gifts" and ptype in ("interest", "recipient"):
        return pillar_title(ptype, key, market, tax)  # already 'Gift Ideas for Dog Lovers'
    if ptype == "occasion" and tax and key in tax["facets"]["occasion"]["values"]:
        spec = tax["facets"]["occasion"]["values"][key]
        occ = spec.get("label_uk") if market == "uk" and spec.get("label_uk") else spec["label"]
        return f"{occ} {label}"
    return f"{pillar_title(ptype, key, market, tax)}: {label}"


def split_by_theme(groups: dict, tax: dict | None, max_size: int, min_clusters: int, max_sub: int):
    """Split every pillar group with more than max_size clusters into one group per theme.

    A theme becomes a pillar when it has >= min_clusters clusters and enough volume (>= 500 and >= 2% of the group's
    volume outside its biggest theme, so one huge theme such as 'dates' does not hide the others). A theme that is too
    small joins its fallback theme when that one is a pillar. What is left (no theme, or a small theme without a
    fallback) is miscellaneous: a cluster that reaches the theme volume threshold on its own becomes a standalone
    post, the rest goes to the backlog (not planned as posts)."""
    specs, order = theme_specs(tax)
    out: dict[tuple, tuple[list[dict], str]] = {}
    backlog: list[tuple[dict, tuple]] = []
    standalone: list[tuple[dict, tuple]] = []
    split_notes: dict[tuple, dict] = {}
    for gkey, members in groups.items():
        market, ptype, key = gkey
        by: dict[str, list[dict]] = defaultdict(list)
        for m in members:
            by[m.get("theme", "") or ""].append(m)
        if len(members) <= max_size or set(by) <= {""}:
            out[gkey] = (members, "")
            continue
        vol = {t: sum(volume(r) for r in rows) for t, rows in by.items()}
        themed = sorted((t for t in by if t), key=lambda t: (-vol[t], order.index(t) if t in order else 99))
        rest_vol = sum(vol.values()) - (vol[themed[0]] if themed else 0)
        min_vol = max(500, 0.02 * rest_vol)
        qualified = [t for i, t in enumerate(themed)
                     if len(by[t]) >= min_clusters and (i == 0 or vol[t] >= min_vol)][:max_sub]
        final: dict[str, list[dict]] = defaultdict(list)
        residual: list[dict] = []
        for t, rows in by.items():
            target = t if t in qualified else specs.get(t, {}).get("fallback") if t else None
            if target in qualified:
                final[target].extend(rows)
            else:
                residual.extend(rows)
        for t in qualified:
            out[(market, ptype, f"{key}/{t}")] = (final[t], t)
        for r in residual:
            if volume(r) >= min_vol:
                standalone.append((r, gkey))
            else:
                backlog.append((r, gkey))
        split_notes[gkey] = {"themes": set(qualified)}
    return out, backlog, standalone, split_notes


def choose_theme_hub(rows: list[dict]) -> dict:
    """Hub of a theme pillar: the broadest cluster (empty core: 'history of thanksgiving', 'when is thanksgiving'),
    else the strongest one."""
    broad = [r for r in rows if not core_of(r)]
    return max(broad or rows, key=lambda r: (volume(r), priority_score(r)))


# Words that say who or when, not what: they narrow a post without making it a different post
# ('thanksgiving books for kids' is the 'books' post, 'places to travel thanksgiving weekend' is the 'travel' post).
MODIFIERS = frozenset({"kids", "adults", "family", "teen", "teens", "teenager", "seniors", "group", "youth", "couples",
                       "men", "women", "students", "week", "weekend", "break", "time", "night", "today", "year", "years"})
REFINE_SHARE = 0.10


def specificity(node: frozenset) -> tuple[int, int]:
    """Subject words count first: 'thanksgiving books for kids' belongs to the 'books' post rather than to 'kids'."""
    return (len(node - MODIFIERS), len(node))


def fluency_of(r: dict) -> float:
    try:
        return float(r.get("name_fluency") or -99)
    except ValueError:
        return -99.0


def representative(node: frozenset, rows: list[dict]) -> dict:
    """The cluster that names a sub-topic post: the strongest one by its main keyword's volume AND its cluster's total
    (geometric mean, so neither one big variant nor a long tail of tiny ones decides alone), discounted when it is
    narrower than the sub-topic (who/when words do not narrow it), then the most natural name."""
    def key(r):
        extra = len((core_of(r) - node) - MODIFIERS)
        strength = (max(1, to_int(r.get("seed_volume"), volume(r))) * max(1, volume(r))) ** 0.5
        return (strength / (1 + 0.5 * extra), fluency_of(r), volume(r))
    return max(rows, key=key)


def nearest_post(r: dict, targets: list[dict], hub: dict) -> dict:
    """Kept post that the cluster r is merged into: a post whose core is contained in r's core (r is a narrower version
    of it, the most specific such post wins), else the post sharing most of r's core, else the pillar hub."""
    cr, best, best_score = core_of(r), hub, (0.5, 0.0, 0)
    for t in targets:
        ct = core_of(t)
        if ct and ct <= cr:
            score = (2.0 + len(ct), 0.0, volume(t))
        elif (ct & cr) - MODIFIERS:  # sharing only 'kids' does not make 'thanksgiving for kids' a books post
            score = (1.0, len(ct & cr) / len(ct | cr), volume(t))
        else:
            continue
        if score > best_score:
            best, best_score = t, score
    return best


def select_posts(hub: dict | None, members: list[dict], max_posts: int, min_post_volume: int,
                 min_post_share: float = 0.02, keep_volume: int = 2000, small_pillar: int = 12):
    """Return (kept clusters, {cluster_id: target row}) for one pillar. max_posts=0 means no cap on the number of
    posts: the volume thresholds alone decide, and a pillar of up to small_pillar clusters keeps all of them. With
    max_posts > 0 nothing is merged unless the pillar has more than max_posts clusters, and at most max_posts are kept.

    Candidate sub-topics are the clusters' cores and every single word of them. Greedily, the sub-topic that would own
    the most volume (clusters whose core contains it and that no more specific kept sub-topic owns yet) is kept while
    it owns enough: >= min_post_volume, >= min_post_share of the volume outside the hub and >= 10% of the strongest
    sub-topic, except that a sub-topic owning >= keep_volume is always worth a post ('thanksgiving story for
    kindergarten', 4,640, next to 'the first thanksgiving', 158,000). The post is named after its representative
    cluster; the other clusters it owns are merged into it."""
    others = [m for m in members if hub is None or m["cluster_id"] != hub["cluster_id"]]
    if len(members) <= (max_posts or small_pillar):
        return others, {}
    base = core_of(hub) if hub else frozenset()
    floor = max(min_post_volume, min_post_share * sum(volume(r) for r in others))
    threshold = max(min_post_volume, min(floor, keep_volume))
    postings: dict[str, list[dict]] = defaultdict(list)
    for r in others:
        for t in core_of(r):
            postings[t].append(r)
    nodes = {core_of(r) for r in others} | {frozenset([t]) for t in postings}
    nodes = {n for n in nodes if n and not n <= base}
    sup = {n: [r for r in postings[min(n, key=lambda t: len(postings[t]))] if n <= core_of(r)] for n in nodes}
    owner = {r["cluster_id"]: base for r in others}
    selected: list[frozenset] = []
    gain_of: dict[frozenset, int] = {}
    while not max_posts or len(selected) < max_posts - (1 if hub else 0):
        best = None
        for n in nodes:
            if n in gain_of:
                continue
            g = sum(volume(r) for r in sup[n] if specificity(n) > specificity(owner[r["cluster_id"]]))
            if g < threshold:
                continue
            if any(p < n and ((n - p) <= MODIFIERS or g < REFINE_SHARE * gain_of[p]) for p in selected):
                continue  # 'books for kids' is a section of 'books'; a tiny narrowing of a kept post too
            if best is None or (g, -len(n), sorted(n)) > (best[0], -len(best[1]), sorted(best[1])):
                best = (g, n)
        if best is None:
            break
        g, n = best
        selected.append(n)
        gain_of[n] = g
        if len(selected) == 1:  # the strongest sub-topic sets the bar for the others (capped by keep_volume)
            threshold = max(min_post_volume, min(max(floor, 0.1 * g), keep_volume))
        for r in sup[n]:
            if specificity(n) > specificity(owner[r["cluster_id"]]):
                owner[r["cluster_id"]] = n
    owned: dict[frozenset, list[dict]] = defaultdict(list)
    for r in others:
        owned[owner[r["cluster_id"]]].append(r)
    kept, rep_of = [], {}
    for n in selected:
        rows = owned.get(n, [])
        if rows and sum(volume(r) for r in rows) >= threshold / 2:  # a later, narrower sub-topic may have taken most of it
            rep_of[n] = representative(n, rows)
            kept.append(rep_of[n])
    if not kept and hub is None and others:  # a virtual pillar still needs one real post to merge the rest into
        kept = [max(others, key=lambda r: (priority_score(r), volume(r)))]
    kept_ids = {r["cluster_id"] for r in kept}
    targets = kept + ([hub] if hub else [])
    anchor = hub or max(kept, key=volume)
    merged = {r["cluster_id"]: rep_of.get(owner[r["cluster_id"]]) or nearest_post(r, targets, anchor)
              for r in others if r["cluster_id"] not in kept_ids}
    return kept, merged


def adopt(r: dict, candidates: list[tuple[dict, tuple]]):
    """Theme pillar that a long-tail cluster without a theme pillar belongs to: the one holding a cluster that asks the
    same thing ('thanksgiving names' {name} -> the pillar of 'another name for thanksgiving' {name}): that cluster's
    core is contained in r's core, or they share subject words with half of their words in common. None when
    nothing matches: r stays in the backlog."""
    cr, best, best_score = core_of(r), None, None
    if not cr - MODIFIERS:
        return None
    for m, gkey in candidates:
        cm = core_of(m)
        if not cm - MODIFIERS:
            continue
        if cm <= cr:
            score = (2, len(cm), volume(m))
        elif (cm & cr) - MODIFIERS and len(cm & cr) / len(cm | cr) >= 0.5:
            score = (1, len(cm & cr), volume(m))
        else:
            continue
        if best_score is None or score > best_score:
            best, best_score = gkey, score
    return best


def facet_cols(r: dict) -> dict:
    return {"season": r.get("season", ""), "occasion": r.get("occasion", ""), "recipient": r.get("recipient", ""),
            "interest": r.get("interest", ""), "product": r.get("product", ""), "craft": r.get("craft", ""),
            "theme": r.get("theme", "")}


NAME_FILLER = {"the", "a", "an", "of", "in", "on", "for", "to", "is", "are", "was", "were", "do", "does", "did", "and",
               "what", "when", "where", "why", "how", "who", "which", "we", "you", "it", "its", "this", "that", "with",
               "about", "at", "by", "celebrate", "celebrated", "celebrating", "celebration", "always", "ever", "really",
               "day", "america", "american", "usa", "us", "happy"}


def name_words(name: str, topic_words: set[str]) -> set[str]:
    out = set()
    for t in re.findall(r"[a-z0-9]+", name.lower().replace("'", "")):
        if t in NAME_FILLER or t in topic_words:
            continue
        out.add(t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith(("ss", "us", "is")) else t)
    return out


def dedupe_across_pillars(plans: list[dict]) -> None:
    """Two theme pillars of one topic must not plan the same post: 'why do we celebrate thanksgiving on thursday'
    (meaning) and 'is thanksgiving always on a thursday' (dates) share the core {thursday} and the word 'thursday'. The
    smaller post joins the larger one, with every cluster merged into it. The names must share most of their words too,
    because a theme's own words are not in the core: 'true meaning of thanksgiving' and 'true story of thanksgiving'
    both have the core {real} but are different posts. Who/when-only cores ({kids}) are left alone."""
    by_core: dict[tuple, list[tuple[dict, dict]]] = defaultdict(list)
    for plan in plans:
        if not plan["theme"]:
            continue
        for r in plan["kept"]:
            c = core_of(r)
            if c - MODIFIERS:
                by_core[(plan["topic"], c)].append((plan, r))

    def owned(plan: dict, r: dict) -> int:
        return volume(r) + sum(volume(m) for m in plan["members"]
                               if plan["merged"].get(m["cluster_id"]) is r)
    for (topic, _), posts in by_core.items():
        if len({id(p) for p, _ in posts}) < 2:
            continue
        win_plan, winner = max(posts, key=lambda pr: owned(*pr))
        topic_words = set(topic[2].replace("-", " ").split())
        win_words = name_words(winner["cluster_name"], topic_words)
        for plan, r in posts:
            words = name_words(r["cluster_name"], topic_words)
            if r is winner or not (words | win_words) or len(words & win_words) / len(words | win_words) < 0.5:
                continue
            plan["kept"] = [k for k in plan["kept"] if k is not r]
            plan["merged"] = {cid: (winner if t is r else t) for cid, t in plan["merged"].items()}
            plan["merged"][r["cluster_id"]] = winner


# --------------------------------------------------------------------------- decisions (topic step)
# The decisions file is a shared data contract (printerval-blog-seo/references/data-contracts.md) that each skill
# reads itself. This step applies its own five actions, ignores the other steps' actions and logs each of its own.
TOPIC_ACTIONS = ("promote_pillar", "demote_pillar", "set_pillar", "restore_backlog", "drop_post")  # applied in this order
LOG_FIELDS = ["decision_id", "step", "action", "market", "keyword", "target", "value", "author", "status", "detail"]
QUOTES = str.maketrans({"‘": "'", "’": "'", "ʼ": "'", "“": '"', "”": '"'})
XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def decision_key(text: str) -> str:
    """Matching key of the decisions contract: NFC, lowercase, straight quotes, no apostrophes, '-'/'_' as spaces."""
    t = unicodedata.normalize("NFC", text or "").lower().translate(QUOTES).replace("'", "")
    return " ".join(t.replace("-", " ").replace("_", " ").split())


def xlsx_rows(path: str) -> list[list[str]]:
    """Cells of the sheet 'Decisions' of an .xlsx, else of its first sheet."""
    rel_id = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        shared = ([] if "xl/sharedStrings.xml" not in names else
                  ["".join(t.text or "" for t in si.iter(XLSX_NS + "t"))
                   for si in ET.fromstring(zf.read("xl/sharedStrings.xml")).iter(XLSX_NS + "si")])
        target = {r.get("Id"): r.get("Target") for r in ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))}
        sheets = [(s.get("name"), target[s.get(rel_id)])
                  for s in ET.fromstring(zf.read("xl/workbook.xml")).iter(XLSX_NS + "sheet")]
        part = next((s for s in sheets if s[0] == "Decisions"), sheets[0])[1]
        part = part.lstrip("/") if part.startswith("/") else "xl/" + part
        rows = []
        for row in ET.fromstring(zf.read(part)).iter(XLSX_NS + "row"):
            cells: dict[int, str] = {}
            for c in row.iter(XLSX_NS + "c"):
                col = 0
                for ch in re.match(r"[A-Z]*", c.get("r", "")).group():
                    col = col * 26 + ord(ch) - 64
                v = c.find(XLSX_NS + "v")
                if c.get("t") == "s" and v is not None:
                    val = shared[int(v.text)]
                elif c.get("t") == "inlineStr":
                    val = "".join(t.text or "" for t in c.iter(XLSX_NS + "t"))
                else:
                    val = v.text if v is not None and v.text else ""
                cells[(col or len(cells) + 1) - 1] = val
            rows.append([cells.get(i, "") for i in range(max(cells, default=-1) + 1)])
    return rows


def read_decisions(path: str) -> list[dict]:
    """Rows of a decisions file (CSV, or the .xlsx sheet 'Decisions' or first sheet) keyed by lowercase header."""
    if path.lower().endswith((".xlsx", ".xlsm")):
        rows = xlsx_rows(path)
    else:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.reader(fh))
    for h, row in enumerate(rows):
        header = [str(c).strip().lower() for c in row]
        if "decision_id" in header and "action" in header:
            return [{k: str(v).strip() for k, v in zip(header, r) if k} for r in rows[h + 1:] if any(str(v).strip() for v in r)]
    raise SystemExit(f"{path}: no header with decision_id and action")


def apply_topic_decisions(decisions: list[dict], plans: list[dict], leftovers: list[dict], extra: list[tuple],
                          backlog: list[dict], skipped: list[dict], dec_of: dict, note_of: dict) -> list[dict]:
    """Apply this step's decisions to the plan in place (TOPIC_ACTIONS order, then decision_id order); return the log.
    A post that moves to another pillar keeps the clusters merged into it (they may point across pillars, as after
    dedupe_across_pillars); a post that leaves the plan hands them to its pillar's hub or biggest post, else to the
    backlog. Two decisions with opposite effects on one keyword are both 'conflict' and neither is applied."""
    live = [m for p in plans for m in p["members"]] + leftovers + [r for r, _ in extra] + backlog + skipped
    by_main: dict[str, list[dict]] = defaultdict(list)
    by_member: dict[str, list[dict]] = defaultdict(list)
    for r in live:
        by_main[decision_key(r["cluster_name"])].append(r)
        for k in (r.get("keywords") or "").split("|"):
            if k.strip() and not any(x is r for x in by_member[decision_key(k)]):
                by_member[decision_key(k)].append(r)

    def where(r: dict) -> tuple[str, dict | None]:
        for p in plans:
            if p["chosen"] is r:
                return "hub", p
            if any(k is r for k in p["kept"]):
                return "post", p
            if r["cluster_id"] in p["merged"] and any(m is r for m in p["members"]):
                return "merged", p
        if any(x is r for x in leftovers) or any(x is r for x, _ in extra):
            return "standalone", None
        return ("backlog" if any(x is r for x in backlog) else "skip"), None

    def find(text: str, market: str):
        key = decision_key(text)
        hits = [r for r in by_main.get(key, []) if not market or r["market"] == market]
        hits = hits or [r for r in by_member.get(key, []) if not market or r["market"] == market]
        if len({r["market"] for r in hits}) > 1:
            return None, "invalid", f"'{text}' is in several markets: set market"
        if hits:
            return hits[0], "", ""
        words = set(key.split())
        pool = [r for r in live if not market or r["market"] == market]
        shared = lambda r: len(words & set(decision_key(r["cluster_name"]).split()))  # noqa: E731
        close = max(pool, key=lambda r: (shared(r), volume(r)), default=None)
        return None, "stale", f"'{text}' not found" + (f"; closest: '{close['cluster_name']}'" if close and shared(close)
                                                       else "; no keyword shares a word with it")

    def detach(r: dict, keep_children: bool) -> None:
        kind, p = where(r)
        if p is not None:
            if kind == "hub":
                p["chosen"], p["no_pillar"] = None, True
            p["kept"] = [k for k in p["kept"] if k is not r]
            p["merged"].pop(r["cluster_id"], None)
            p["members"] = [m for m in p["members"] if m is not r]
        leftovers[:] = [x for x in leftovers if x is not r]
        extra[:] = [(x, g) for x, g in extra if x is not r]
        backlog[:] = [x for x in backlog if x is not r]
        skipped[:] = [x for x in skipped if x is not r]
        if keep_children:
            return
        for q in plans:  # the clusters merged into r go to their own pillar's hub or biggest post
            for cid, t in list(q["merged"].items()):
                if t is r:
                    anchor = q["chosen"] or max(q["kept"], key=volume, default=None)
                    if anchor is not None:
                        q["merged"][cid] = anchor
                    else:
                        child = next(m for m in q["members"] if m["cluster_id"] == cid)
                        del q["merged"][cid]
                        q["members"] = [m for m in q["members"] if m is not child]
                        backlog.append(child)

    def join(r: dict, p: dict) -> None:
        p["members"].append(r)
        p["kept"].append(r)

    log, todo = [], []
    for d in decisions:
        action = (d.get("action") or "").strip().lower()
        if action not in TOPIC_ACTIONS:
            continue  # another step's action: not logged here
        e = {"decision_id": d.get("decision_id", ""), "step": "topic", "action": action,
             "market": (d.get("market") or "").strip().lower(), "keyword": d.get("keyword", ""),
             "target": d.get("target", ""), "value": d.get("value", ""), "author": d.get("author", ""),
             "status": "", "detail": ""}
        log.append(e)
        if not (d.get("reason") or "").strip() or not (d.get("evidence") or "").strip():
            e.update(status="invalid", detail="reason and evidence are required")
        elif e["market"] not in ("", "us", "uk"):
            e.update(status="invalid", detail=f"unknown market '{e['market']}'")
        elif not decision_key(e["keyword"]):
            e.update(status="invalid", detail="keyword is empty")
        else:
            todo.append(e)
    by_kw: dict[tuple, list[dict]] = defaultdict(list)
    for e in todo:
        by_kw[(e["market"], decision_key(e["keyword"]))].append(e)
    for group in by_kw.values():
        acts, clash = {e["action"] for e in group}, set()
        if {"promote_pillar", "demote_pillar"} <= acts:
            clash |= {id(e) for e in group if e["action"] in ("promote_pillar", "demote_pillar")}
        if "drop_post" in acts and len(acts) > 1:
            clash |= {id(e) for e in group}
        if len({decision_key(e["target"]) for e in group if e["action"] == "set_pillar"}) > 1:
            clash |= {id(e) for e in group if e["action"] == "set_pillar"}
        for e in group:
            if id(e) in clash:
                e.update(status="conflict", detail="conflicts with " + ", ".join(
                    x["decision_id"] for x in group if id(x) in clash and x is not e))
    for e in sorted((e for e in todo if not e["status"]), key=lambda e: (TOPIC_ACTIONS.index(e["action"]), e["decision_id"])):
        r, status, detail = find(e["keyword"], e["market"])
        if r is None:
            e.update(status=status, detail=detail)
            continue
        e["market"] = r["market"]
        kind, p = where(r)
        was = kind + (f" in {p['pid']}" if p else "")
        act, status, detail = e["action"], "applied", ""
        if kind == "skip" and act != "drop_post":
            status, detail = "invalid", "a skipped cluster (pure shopping): change its need in the cluster step (set_need)"
        elif act == "promote_pillar":
            if kind == "hub":
                status, detail = "already_true", f"already the hub of {p['pid']}"
            elif p is not None:
                old = p["chosen"]
                p["kept"] = [k for k in p["kept"] if k is not r] + ([old] if old is not None else [])
                p["merged"].pop(r["cluster_id"], None)
                p["chosen"], p["no_pillar"], p["promoted"] = r, False, False
                detail = f"hub of {p['pid']} (was {kind})" + (f"; '{old['cluster_name']}' becomes a cluster post" if old else "")
            else:
                detach(r, True)
                pid, name = f"P{len(plans) + 1:02d}", r["cluster_name"]
                ptype = next((f for f in ("occasion", "interest", "recipient", "craft", "product") if r.get(f)), "topic")
                plans.append({"pid": pid, "promoted": False, "no_pillar": False, "theme": "", "members": [r], "chosen": r,
                              "kept": [], "merged": {}, "topic": (r["market"], ptype, slugify(name)),
                              "base": {"pillar_id": pid, "pillar_type": ptype, "pillar_key": slugify(name),
                                       "pillar_name": name[:1].upper() + name[1:], "market": r["market"]}})
                detail = f"new pillar {pid} (was {kind}); move posts under it with set_pillar"
            if status == "applied":
                note_of[r["cluster_id"]] = (f"pillar by decision {e['decision_id']}; write it as a hub that covers "
                                            "the clusters below")
        elif act == "demote_pillar":
            if kind != "hub":
                status, detail = "already_true", f"not a pillar hub ({was})"
            else:
                p["chosen"], p["no_pillar"] = None, True
                p["kept"].append(r)
                detail = f"cluster post of {p['pid']}, which has no pillar hub now"
        elif act == "set_pillar" and decision_key(e["target"]) in ("", "none"):
            if kind == "hub":
                status, detail = "invalid", f"the hub of {p['pid']}: demote_pillar it first"
            elif kind == "standalone":
                status, detail = "already_true", "already a standalone post"
            else:
                detach(r, False)
                leftovers.append(r)
                detail = f"standalone post (was {was})"
                note_of[r["cluster_id"]] = f"no pillar by decision {e['decision_id']}: write it on its own"
        elif act in ("set_pillar", "restore_backlog") and (e["target"] or "").strip():
            t, tstatus, tdetail = find(e["target"], r["market"])
            tkind, tp = where(t) if t is not None else ("", None)
            ok = ("hub",) if act == "set_pillar" else ("hub", "post", "standalone")
            if t is None:
                status, detail = tstatus, "target " + tdetail
            elif tkind not in ok:
                status, detail = "invalid", (f"target '{t['cluster_name']}' is not a pillar hub ({tkind}): promote_pillar it first"
                                             if act == "set_pillar" else f"target '{t['cluster_name']}' is not planned ({tkind})")
            elif kind == "hub":
                status, detail = "invalid", f"the hub of {p['pid']}: demote_pillar it first"
            elif act == "restore_backlog" and kind in ("post", "standalone"):
                status, detail = "already_true", f"already planned ({was})"
            elif kind == "post" and p is tp:
                status, detail = "already_true", f"already a post of {tp['pid']}"
            else:
                detach(r, True)
                if tp is None:
                    leftovers.append(r)
                else:
                    join(r, tp)
                detail = (f"post of {tp['pid']}" if tp else "standalone post") + f" next to '{t['cluster_name']}' (was {was})"
        elif act == "restore_backlog":
            if kind in ("hub", "post", "standalone"):
                status, detail = "already_true", f"already planned ({was})"
            elif kind == "merged":
                p["merged"].pop(r["cluster_id"], None)
                p["kept"].append(r)
                detail = f"post of {p['pid']} (was merged)"
            else:
                detach(r, True)
                leftovers.append(r)
                detail = "standalone post (was backlog)"
        elif act == "drop_post":
            if kind == "skip":
                status, detail = "already_true", "already skipped"
            else:
                detach(r, False)
                skipped.append(r)
                detail = f"skipped (was {was})"
                note_of[r["cluster_id"]] = (f"dropped by decision {e['decision_id']}: "
                                            + ((e["value"] or "").strip() or "see the decisions file"))
        e.update(status=status, detail=detail)
        if status == "applied":
            dec_of[r["cluster_id"]].append(e["decision_id"])
    return log


def build(rows: list[dict], priority: list[str], min_clusters: int, tax: dict | None, max_pillar_size: int = 30,
          max_posts: int = 0, min_post_volume: int = 300, max_sub_pillars: int = 10, target_posts: int = 0,
          min_post_share: float = 0.02, keep_volume: int = 2000, small_pillar: int = 12,
          promote_min_volume: int = 50, promote_min_share: float = 0.15,
          decisions: list[dict] | None = None, decision_log: list[dict] | None = None):
    live = [r for r in rows if r["blog_fit"] != "low"]
    skipped = [r for r in rows if r["blog_fit"] == "low"]
    seo_items, seo_hub, live = seo_pillars(live)  # the SEO's own pillars first: the engine groups the rest
    real, leftovers = assign_groups(live, priority, min_clusters)
    groups, backlog, extra_standalone, split_notes = split_by_theme(real, tax, max_pillar_size, min_clusters, max_sub_pillars)
    members_of_topic: dict[tuple, list[tuple[dict, tuple]]] = defaultdict(list)
    for gkey, (members, theme) in groups.items():
        if theme:
            members_of_topic[(gkey[0], gkey[1], gkey[2].split("/", 1)[0])] += [(m, gkey) for m in members]
    still = []
    for r, topic in backlog:  # long tail WITHOUT a theme joins the theme pillar that asks the same thing, if any
        target = None if r.get("theme") else adopt(r, members_of_topic.get(topic, []))
        if target:
            groups[target][0].append(r)
        else:
            still.append(r)
    backlog = still
    # In a pillar that is too big, a cluster must also be among the target_posts largest clusters of the file to stay
    # a post of its own; this keeps the plan around target_posts posts however long the export is.
    vols = sorted((volume(r) for r in live), reverse=True)
    if target_posts and len(vols) > target_posts:
        min_post_volume = max(min_post_volume, vols[target_posts - 1])

    out, gaps, used_slugs = [], {}, set()

    def unique_slug(text: str) -> str:
        base, n, slug = slugify(text), 1, slugify(text)
        while slug in used_slugs:
            n += 1
            slug = f"{base}-{n}"
        used_slugs.add(slug)
        return slug

    def post_row(base: dict, r: dict, role: str, slug: str, note: str = "", merged_into: str = "") -> dict:
        return {**base, "role": role, "cluster_id": r["cluster_id"], "primary_keyword": r["cluster_name"],
                "planned_slug": slug, "post_type": post_type(r, False) if role != "merged" else "merged",
                "reader_need": r["reader_need"], "cluster_volume": volume(r),
                "priority_score": priority_score(r) if role != "merged" else 0, **facet_cols(r),
                "keywords": r["keywords"], "parent_hint": "", "note": note, "merged_into": merged_into}

    ordered = sorted(list(groups.items()) + seo_items, key=lambda kv: -sum(volume(r) for r in kv[1][0]))
    pillar_ids, plans = {}, []
    for n, ((market, ptype, key), (members, theme)) in enumerate(ordered, 1):
        pid = f"P{n:02d}"
        pillar_ids[(market, ptype, key)] = pid
        hub = seo_hub.get((market, ptype, key))
        if hub is not None:  # the SEO's pillar: hub and posts as the grouped file set them
            name = hub["cluster_name"]
            plans.append({"pid": pid, "promoted": False, "no_pillar": False, "seo": True, "theme": "", "members": members,
                          "chosen": hub, "kept": [m for m in members if m is not hub], "merged": {},
                          "topic": (market, ptype, key),
                          "base": {"pillar_id": pid, "pillar_type": ptype, "pillar_key": key,
                                   "pillar_name": name[:1].upper() + name[1:], "market": market}})
            continue
        title = theme_pillar_title(ptype, key.split("/", 1)[0], theme, market, tax) if theme else pillar_title(ptype, key, market, tax)
        chosen = choose_theme_hub(members) if theme else choose_pillar_cluster(members, ptype)
        promoted = False
        broad = [r for r in members if theme or not narrower_facets(r, ptype)]
        if chosen is None and broad:  # no broad head keyword: the strongest broad cluster becomes the real pillar if strong enough
            top = max(broad, key=lambda r: (volume(r), priority_score(r)))
            total = sum(volume(r) for r in members)
            if volume(top) >= promote_min_volume and total and volume(top) / total >= promote_min_share:
                chosen, promoted = top, True
        kept, merged = select_posts(chosen, members, max_posts, min_post_volume, min_post_share, keep_volume, small_pillar)
        plans.append({"pid": pid, "promoted": promoted, "no_pillar": chosen is None, "theme": theme, "members": members, "chosen": chosen, "kept": kept, "merged": merged,
                      "topic": (market, ptype, key.split("/", 1)[0]),
                      "base": {"pillar_id": pid, "pillar_type": ptype, "pillar_key": key, "pillar_name": title,
                               "market": market}})
    dedupe_across_pillars(plans)
    dec_of: dict[str, list[str]] = defaultdict(list)  # cluster_id -> decisions applied to it
    note_of: dict[str, str] = {}
    if decisions:
        log = apply_topic_decisions(decisions, plans, leftovers, extra_standalone, backlog, skipped, dec_of, note_of)
        if decision_log is not None:
            decision_log.extend(log)
    slug_of: dict[str, str] = {}
    for plan in plans:  # slugs first, in plan order, so a post merged across pillars can point to its target
        if plan["chosen"]:
            slug_of[plan["chosen"]["cluster_id"]] = unique_slug(plan["chosen"]["cluster_name"])
        for r in sorted(plan["kept"], key=lambda r: -volume(r)):
            slug_of[r["cluster_id"]] = unique_slug(r["cluster_name"])
    for plan in plans:
        base, chosen, members, theme = plan["base"], plan["chosen"], plan["members"], plan["theme"]
        pid, ptype = plan["pid"], base["pillar_type"]
        total = sum(volume(r) for r in members)
        seasons = {r.get("season", "") for r in members if r.get("season")}
        if chosen:
            out.append({**base, "role": "pillar", "cluster_id": chosen["cluster_id"],
                        "primary_keyword": chosen["cluster_name"], "planned_slug": slug_of[chosen["cluster_id"]],
                        "post_type": "pillar-hub", "reader_need": chosen["reader_need"],
                        "cluster_volume": volume(chosen), "priority_score": priority_score(chosen),
                        **facet_cols(chosen), "keywords": chosen["keywords"], "parent_hint": "",
                        "note": ("pillar set by the SEO's grouped file (Category Kind / Thuộc Pillar); write it as a hub that "
                                 "covers the clusters below" if plan.get("seo") else
                                 f"promoted to real pillar: strongest cluster of the group ({volume(chosen):,} of {total:,}), no broad head keyword; "
                                 "write it as a hub that covers the clusters below" if plan["promoted"] else
                                 f"pillar chosen from cluster {chosen['cluster_id']}; write it as a hub that covers the clusters below"),
                        "merged_into": ""})
        for r in sorted(plan["kept"], key=lambda r: -volume(r)):
            out.append(post_row(base, r, "cluster", slug_of[r["cluster_id"]], note=NO_PILLAR_NOTE if plan["no_pillar"] else ""))
        for r in sorted((m for m in members if m["cluster_id"] in plan["merged"]), key=lambda r: -volume(r)):
            target = plan["merged"][r["cluster_id"]]
            out.append(post_row(base, r, "merged", "", merged_into=slug_of.get(target["cluster_id"], ""),
                                note=f"merged into '{target['cluster_name']}': cover it as a section or as secondary keywords"))
        needs = {r["reader_need"] for r in members}
        if ptype in EXPECTED_BY_TYPE and not theme:
            missing = [s for s in EXPECTED_BY_TYPE[ptype] if not has_need(needs, s)]
            if missing:
                gaps[pid] = [(s, GAP_HINT[s.split("|")[0]]) for s in missing]

    # a split topic (one-occasion export): name the themes the blog would need but the file barely covers
    first_pid = {}
    for (market, ptype, key), pid in pillar_ids.items():
        first_pid.setdefault((market, ptype, key.split("/", 1)[0]), pid)
    for gkey, info in split_notes.items():
        missing = [t for t in THEME_GAPS if t not in info["themes"]]
        pid = first_pid.get(gkey)
        if missing and pid:
            label = pillar_title(gkey[1], gkey[2], gkey[0], tax).replace(" Gift Ideas", "")
            gaps.setdefault(pid, []).extend((f"theme:{t}", THEME_GAPS[t].format(topic=label.lower())) for t in missing)

    keys_by_market = {(m, k): pid for (m, t, k), pid in pillar_ids.items()}
    for (market, ptype, key), pid in first_pid.items():  # a split topic points to its biggest theme pillar
        keys_by_market.setdefault((market, key), pid)
    hint_of_extra = {id(r): first_pid.get(gkey, "") for r, gkey in extra_standalone}
    for r in sorted(leftovers + [r for r, _ in extra_standalone], key=lambda r: -volume(r)):
        hint = hint_of_extra.get(id(r), "")
        for facet in ("interest", "recipient", "occasion", "craft", "product"):
            if hint:
                break
            pid = keys_by_market.get((r["market"], r.get(facet, "")))
            if r.get(facet) and pid:
                hint = pid
                break
        out.append({"pillar_id": "", "pillar_type": "", "pillar_key": "", "pillar_name": "", "market": r["market"],
                    "role": "standalone", "cluster_id": r["cluster_id"], "primary_keyword": r["cluster_name"],
                    "planned_slug": unique_slug(r["cluster_name"]), "post_type": post_type(r, False),
                    "reader_need": r["reader_need"], "cluster_volume": volume(r),
                    "priority_score": priority_score(r), **facet_cols(r),
                    "keywords": r["keywords"], "parent_hint": hint,
                    "note": ("no theme pillar fits this post: write it on its own and link it to the suggested pillar"
                             if id(r) in hint_of_extra else
                             "fewer than %d clusters in this group: write as a standalone post, link to the suggested pillar if there is one" % min_clusters),
                    "merged_into": ""})
    for r in sorted(backlog, key=lambda r: -volume(r)):
        out.append({"pillar_id": "", "pillar_type": "", "pillar_key": "", "pillar_name": "", "market": r["market"],
                    "role": "backlog", "cluster_id": r["cluster_id"], "primary_keyword": r["cluster_name"],
                    "planned_slug": "", "post_type": "backlog", "reader_need": r["reader_need"],
                    "cluster_volume": volume(r), "priority_score": 0, **facet_cols(r),
                    "keywords": r["keywords"], "parent_hint": "",
                    "note": "long tail without a theme pillar: not planned; reuse as wording ideas or research it again",
                    "merged_into": ""})
    for r in sorted(skipped, key=lambda r: -volume(r)):
        out.append({"pillar_id": "", "pillar_type": "", "pillar_key": "", "pillar_name": "", "market": r["market"],
                    "role": "skip", "cluster_id": r["cluster_id"], "primary_keyword": r["cluster_name"],
                    "planned_slug": "", "post_type": "skip", "reader_need": r["reader_need"],
                    "cluster_volume": volume(r), "priority_score": 0, **facet_cols(r),
                    "keywords": r["keywords"], "parent_hint": "",
                    "note": "pure shopping intent: leave to the shop pages / content team, do not write a blog post",
                    "merged_into": ""})

    ranked = sorted((o for o in out if o["role"] in PLANNED_ROLES), key=lambda o: -o["priority_score"])
    for i, o in enumerate(ranked):
        pct = (i + 1) / max(1, len(ranked))
        o["bucket"] = "A" if pct <= 0.2 else "B" if pct <= 0.5 else "C"
    for o in out:
        o.setdefault("bucket", "")
        o["note"] = note_of.get(o["cluster_id"], o["note"])
        o["decision_ids"] = "|".join(dec_of.get(o["cluster_id"], []))
    return out, gaps


NO_PILLAR_NOTE = "No real pillar yet: research a head keyword for this group; until then link these posts to each other"
PLANNED_ROLES = ("pillar", "cluster", "standalone")
THEME_GAPS = {
    "gifts": "gift ideas, shirts and custom products for {topic} (the closest fit for Printerval): export seed keywords "
             "such as '{topic} gifts', '{topic} shirts', 'personalized {topic} gifts'",
    "messages": "sayings, quotes and card messages for {topic} (they lead naturally to custom products): export "
                "'{topic} quotes', '{topic} sayings', '{topic} captions'",
    "decor": "decor and table ideas for {topic}: export '{topic} decor', '{topic} decorations'",
}

FIELDS = ["pillar_id", "pillar_type", "pillar_key", "pillar_name", "role", "cluster_id", "primary_keyword",
          "planned_slug", "post_type", "reader_need", "cluster_volume", "priority_score", "bucket", "season",
          "market", "occasion", "recipient", "interest", "product", "craft", "keywords", "parent_hint", "note",
          "theme", "merged_into", "decision_ids"]


def write_md(path: str, out: list[dict], gaps: dict) -> None:
    lines = ["# Topic map (pillar/cluster)", ""]
    by_pillar: dict[str, list[dict]] = defaultdict(list)
    merged_vol: dict[str, int] = defaultdict(int)
    merged_n: dict[str, int] = defaultdict(int)
    for o in out:
        if o["pillar_id"]:
            by_pillar[o["pillar_id"]].append(o)
        if o["role"] == "merged":  # a post may also absorb clusters from another theme pillar of its topic
            merged_vol[o["merged_into"]] += o["cluster_volume"]
            merged_n[o["merged_into"]] += 1
    for pid, rows in by_pillar.items():
        head = next((r for r in rows if r["role"] == "pillar"), None)
        first = head or rows[0]
        total = sum(r["cluster_volume"] for r in rows)
        season = f" · season: {first['season']}" if first["season"] else ""
        lines += [f"## {pid} · {first['pillar_name']}  ({first['pillar_type']} · {first['market']}{season})",
                  f"Total cluster volume: {total:,}. "
                  + (f"Pillar: `{head['planned_slug']}` – {head['primary_keyword']}" if head else
                     "**No real pillar yet**: research a head keyword for this group."), "",
                  "| Role | Slug | Post type | Reader need | Volume | + merged clusters | Priority |", "|---|---|---|---|---:|---|---|"]
        for r in rows:
            if r["role"] == "merged":
                continue
            extra = f"{merged_n[r['planned_slug']]} ({merged_vol[r['planned_slug']]:,})" if merged_n.get(r["planned_slug"]) else "-"
            lines.append(f"| {r['role']} | `{r['planned_slug']}` | {r['post_type']} | {r['reader_need']} | "
                         f"{r['cluster_volume']:,} | {extra} | {r['bucket']} |")
        if pid in gaps:
            lines += ["", "**Content gaps:** " + "; ".join(f"missing *{s.replace('|', ' or ')}* ({h})" for s, h in gaps[pid])]
        lines.append("")
    stand = [o for o in out if o["role"] == "standalone"]
    if stand:
        lines += ["## Standalone posts (not enough clusters for a pillar)", "",
                  "| Slug | Post type | Volume | Priority | Suggested pillar |", "|---|---|---:|---|---|"]
        lines += [f"| `{o['planned_slug']}` | {o['post_type']} | {o['cluster_volume']:,} | {o['bucket']} | {o['parent_hint'] or '-'} |"
                  for o in stand]
        lines.append("")
    backlog = [o for o in out if o["role"] == "backlog"]
    if backlog:
        lines += [f"## Backlog ({len(backlog)} long-tail clusters, volume {sum(o['cluster_volume'] for o in backlog):,})", "",
                  "No theme pillar fits them; they are not planned as posts. The largest:", ""]
        lines += [f"- {o['primary_keyword']} ({o['cluster_volume']:,})" for o in backlog[:15]]
        lines.append("")
    skip = [o for o in out if o["role"] == "skip"]
    if skip:
        lines += ["## Skipped (shopping intent, not the blog's job)", ""]
        lines += [f"- {o['primary_keyword']} ({o['cluster_volume']:,})" for o in skip]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clusters", help="clusters.csv from keyword-clustering")
    ap.add_argument("--out", default="outputs")
    ap.add_argument("--priority", default="occasion,interest,recipient,craft",
                    help="order of the facets that decide the pillar (default: occasion,interest,recipient,craft)")
    ap.add_argument("--min-clusters", type=int, default=3)
    ap.add_argument("--max-pillar-size", type=int, default=30,
                    help="split a pillar with more clusters than this into one pillar per theme (default 30)")
    ap.add_argument("--max-posts", type=int, default=0,
                    help="optional cap on posts kept per pillar (hub included); default 0 = no cap, the volume thresholds decide")
    ap.add_argument("--keep-all-up-to", type=int, default=12,
                    help="with no cap, a pillar of at most this many clusters keeps every cluster (default 12)")
    ap.add_argument("--promote-min-volume", type=int, default=50,
                    help="a group with no broad head keyword promotes its strongest cluster to real pillar if it has at least "
                         "this volume (default 50)")
    ap.add_argument("--promote-min-share", type=float, default=0.15,
                    help="... and at least this share of the group's volume (default 0.15)")
    ap.add_argument("--min-post-volume", type=int, default=300,
                    help="in a pillar that is too big, a sub-topic owning less volume than this is merged instead of "
                         "being a post (default 300)")
    ap.add_argument("--min-post-share", type=float, default=0.02,
                    help="... and it must own this share of the pillar's volume outside the hub (default 0.02 = 2%%)")
    ap.add_argument("--keep-volume", type=int, default=2000,
                    help="a sub-topic owning at least this volume is always a post, whatever its share (default 2000)")
    ap.add_argument("--max-sub-pillars", type=int, default=10, help="maximum theme pillars per split topic (default 10)")
    ap.add_argument("--target-posts", type=int, default=0,
                    help="cap the plan size: in a pillar that is too big, a cluster must also be among the N largest "
                         "clusters of the file to stay a post (default 0 = off)")
    ap.add_argument("--taxonomy", default=None)
    ap.add_argument("--decisions", help="decisions file (CSV, or .xlsx sheet Decisions): applies set_pillar, promote_pillar, "
                                        "demote_pillar, restore_backlog and drop_post; log in decisions-log-topic.csv")
    args = ap.parse_args(argv)

    with open(args.clusters, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit("clusters.csv is empty")
    tax = load_taxonomy(args.taxonomy)
    if tax is None:
        print("taxonomy.json not found: pillar names will be derived from the keys.", file=sys.stderr)
    priority = [p.strip() for p in args.priority.split(",") if p.strip()]
    decisions = read_decisions(args.decisions) if args.decisions else None
    log: list[dict] = []
    out, gaps = build(rows, priority, args.min_clusters, tax, args.max_pillar_size, args.max_posts,
                      args.min_post_volume, args.max_sub_pillars, args.target_posts, args.min_post_share,
                      args.keep_volume, args.keep_all_up_to, args.promote_min_volume, args.promote_min_share,
                      decisions, log)
    os.makedirs(args.out, exist_ok=True)
    if decisions is not None:
        with open(os.path.join(args.out, "decisions-log-topic.csv"), "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=LOG_FIELDS)
            w.writeheader()
            w.writerows(log)
        status = defaultdict(int)
        for e in log:
            status[e["status"]] += 1
        print(f"Decisions (topic step): {len(log)} logged" + "".join(f", {k} {v}" for k, v in sorted(status.items()))
              + " (decisions-log-topic.csv)")
    with open(os.path.join(args.out, "topic-map.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out)
    write_md(os.path.join(args.out, "topic-map.md"), out, gaps)
    n_p = len({o["pillar_id"] for o in out if o["role"] == "pillar"})
    n_np = len({o["pillar_id"] for o in out if o["pillar_id"]}) - n_p
    counts = defaultdict(int)
    for o in out:
        counts[o["role"]] += 1
    print(f"{len(rows)} clusters -> {n_p} pillars ({n_np} groups with no real pillar yet) | " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"Written to: {os.path.abspath(args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
