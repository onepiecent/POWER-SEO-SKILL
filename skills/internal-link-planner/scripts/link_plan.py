#!/usr/bin/env python3
"""Plan internal links blog <-> blog, or audit an existing list of links. Standard library only.

Planning mode:
    link_plan.py plan topic-map.csv [--published published.csv] [--out outputs]
      -> link-plan.csv (one proposed link per row) + link-summary.md

Audit mode:
    link_plan.py audit links.csv [--topic-map topic-map.csv] [--out outputs]
      links.csv needs the columns source,target,anchor (from/to/anchor text/link text are also accepted).
      -> link-audit.csv + a printed summary

Scope: links between blog posts only. Links to shop pages are NOT in scope (the content team handles them
through product-slot). The rules rest on Google guidance (crawlable links, descriptive anchors) and industry
convention; figures such as 3-5 links per 1,000 words or a ~50 inbound-link threshold are heuristics from correlational research (Zyppy).

How the plan decides (every link has a type, a placement and a reason in link-plan.csv):
  * up      every post links to its pillar (to_pillar), and a post under a sub-hub also to that sub-hub
            (to_parent): authority flows to the pages that target the broad queries.
  * down    a pillar links to its sub-hubs and to its most valuable direct posts, at most --pillar-links (default 12)
            in the body; a sub-hub links to its own posts (from_parent). A pillar never lists every post: the posts
            under a sub-hub are reached through it (topic-map.csv parent_post).
  * across  up to --max-contextual (default 2) body links to the posts that talk about the same thing (cosine of
            their keyword words >= 0.2, shared words named in the reason). A target the site still has to fight for
            (main KD above its reach: 'stretch' or 'hard') may receive more of these links than an easy one, so the
            links go where they help rank. Posts of another topic are linked only through their pillar
            (cross_pillar, when a facet such as the recipient points to it).
  * related up to --max-related (default 3) posts of the same sub-hub or pillar for the 'Related reading' block,
            the most similar first, never a post already linked in the body.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import defaultdict
from urllib.parse import urlparse

GENERIC_ANCHORS = {"click here", "read more", "here", "this article", "this post", "learn more", "link",
                   "this link", "more", "see more", "check it out", "this guide", "this"}
STOPWORDS = {"the", "a", "an", "of", "in", "on", "for", "to", "is", "are", "was", "were", "do", "does", "did", "and",
             "what", "when", "where", "why", "how", "who", "which", "with", "at", "by", "it", "its", "you", "we", "your",
             "our", "my", "day", "this", "that", "be", "can", "best", "ideas", "idea", "happy"}
CONTEXTUAL_MIN = 0.2  # cosine similarity of two posts' keyword words for a contextual body link
# contextual links a post may receive by how hard its main keyword is for the site (topic-map main_kd_fit)
INBOUND_CONTEXTUAL = {"easy": 2, "unknown": 3, "stretch": 4, "hard": 4, "": 3}
FACETS = ("occasion", "recipient", "interest", "product", "craft")
INBOUND_HEURISTIC_MAX = 50
OUTBOUND_REVIEW_MAX = 15
PILLAR_OUTBOUND_WARN = 30


def to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def slug_of(ref: str) -> str:
    ref = (ref or "").strip()
    if "/" in ref or "." in ref:
        path = urlparse(ref).path if "://" in ref or ref.startswith("/") else ref
        parts = [p for p in re.split(r"[/]", path) if p]
        ref = parts[-1] if parts else ref
    return re.sub(r"\.(html?|php)$", "", ref).lower()


def clean_anchor(text: str) -> str:
    t = text.replace("&", "and").strip()
    return re.sub(r"\s+", " ", t)


def read_csv(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


# --------------------------------------------------------------------------- plan
YEAR_RX = re.compile(r"\b(19|20)\d\d\b")
QUESTION_START_RX = re.compile(r"^(what|when|where|why|how|who|which|is|are|do|does|did|can|should|will)\b")


NUMBER_RX = re.compile(r"\d+")
ANCHOR_SHARE = 0.75  # an anchor keeps >= 75% of the main keyword's words [Convention]
QUESTION_ANY_RX = re.compile(r"\b(what|when|where|why|how|who|which)\b")


def describes(anchor: str, main: str) -> bool:
    """The anchor describes the target page: it names no number the main keyword does not ('10ft christmas tree' is
    not the '9 foot christmas tree' post), and it keeps most of the main keyword's words ('how to attach christmas
    decor to roof' is a section of 'how to decorate christmas outside', not a description of it)."""
    if set(NUMBER_RX.findall(anchor)) - set(NUMBER_RX.findall(main)):
        return False
    low = anchor.lower()
    if QUESTION_ANY_RX.search(low) and not QUESTION_START_RX.match(low):
        return False  # an inverted tool phrasing: 'christmas how to decorate', 'secret santa how to reveal'

    a, m = word_counts([anchor]), word_counts([main])
    return not m or len(set(a) & set(m)) >= ANCHOR_SHARE * len(m)


def anchor_candidates(row: dict) -> list[str]:
    """Descriptive anchors from the target's own keywords. No year (the post is refreshed every year, a year in the
    anchor goes stale), only keywords that describe the page (describes()) and 'our guide to ...' only for a noun
    phrase, not for a question."""
    main = clean_anchor(row["primary_keyword"])
    cands: list[str] = []
    for k in [main] + [clean_anchor(k) for k in row["keywords"].split("|") if k][:10]:
        if 2 <= len(k.split()) <= 8 and not YEAR_RX.search(k) and k.lower() not in {c.lower() for c in cands} \
                and (k == main or describes(k, main)):
            cands.append(k)
    if row["post_type"] == "pillar-hub" and not QUESTION_START_RX.match(main.lower()):
        desc = "our guide to " + " ".join(YEAR_RX.sub(" ", main).split())
        if len(desc.split()) <= 8 and desc not in cands:
            cands.append(desc)
    if not cands:  # a long or dated main keyword: without the year (and a trailing 'this year'), never cut mid-phrase
        plain = re.sub(r"\s+(this|next|last) year$", "", " ".join(YEAR_RX.sub(" ", main).split()))
        cands = [plain or main]
    return cands


def word_counts(texts: list[str]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for text in texts:
        for t in set(re.findall(r"[a-z0-9]+", text.lower().replace("'", ""))):
            if t not in STOPWORDS and not YEAR_RX.fullmatch(t) and len(t) > 1:
                counts[t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith(("ss", "us", "is")) else t] += 1
    return counts


def cosine(a: dict[str, int], b: dict[str, int]) -> float:
    dot = sum(v * b.get(t, 0) for t, v in a.items())
    na, nb = sum(v * v for v in a.values()) ** 0.5, sum(v * v for v in b.values()) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


class Planner:
    def __init__(self, rows: list[dict], published: set[str] | None, max_siblings: int, max_cross: int,
                 max_contextual: int = 2, pillar_links: int = 12, max_related: int = 3):
        self.posts = {r["planned_slug"]: r for r in rows if r["role"] != "skip" and r["planned_slug"]}
        self.published = published
        self.max_siblings, self.max_cross, self.max_contextual = max_siblings, max_cross, max_contextual
        self.pillar_links, self.max_related = pillar_links, max_related
        # the words of each post: its keywords and those of the clusters merged into it, minus the topic word
        # that every post shares ('thanksgiving'), so 'first' or 'native' decide which posts are related
        texts: dict[str, list[str]] = defaultdict(list)
        for r in rows:
            slug = r["planned_slug"] if r["planned_slug"] in self.posts else r.get("merged_into", "")
            if slug in self.posts:
                texts[slug] += [r["primary_keyword"]] + [k for k in r.get("keywords", "").split("|") if k]
        self.words = {s: word_counts(t) for s, t in texts.items()}
        share: dict[str, int] = defaultdict(int)
        for w in self.words.values():
            for t in w:
                share[t] += 1
        common = {t for t, n in share.items() if n >= max(3, 0.5 * len(self.words))}
        self.words = {s: {t: v for t, v in w.items() if t not in common} for s, w in self.words.items()}
        self.links: dict[tuple[str, str], dict] = {}
        self.unresolved: list[tuple[str, str]] = []  # (slug, reason) posts with no natural place to link
        self.later: list[tuple[str, str]] = []  # (slug, note) posts the pillar does not link to in its body
        self.ctx_in: dict[str, int] = defaultdict(int)  # contextual links received
        self.anchor_owner: dict[tuple, str] = {}
        self.anchor_use: dict[str, int] = defaultdict(int)
        self.pillar_slug = {r["pillar_id"]: r["planned_slug"] for r in self.posts.values() if r["role"] == "pillar"}
        self.pillar_by_key = {(r["market"], r["pillar_key"]): r["pillar_id"]
                              for r in self.posts.values() if r["role"] == "pillar"}
        # a theme or SEO pillar ('christmas/decor', 'christmas/seo-...') is also found by its topic: the biggest one
        for r in sorted((r for r in self.posts.values() if r["role"] == "pillar"), key=lambda r: r["pillar_id"]):
            self.pillar_by_key.setdefault((r["market"], self.topic(r)), r["pillar_id"])

    # -- helpers
    def shared(self, a: dict, b: dict) -> int:
        return sum(1 for f in FACETS if a.get(f) and a.get(f) == b.get(f))

    def pick_anchor(self, target: dict, source: dict | None = None) -> tuple[str, str]:
        """Diverse, descriptive anchors. The target's URL always comes from its MAIN keyword; the anchor does not have
        to be it. Candidates are the main keyword and the target's secondary keywords. Each exact text is used as
        little as possible, one text never points at two targets (cannibalisation), the candidate that best fits the
        SOURCE post's own wording comes first (semantic context), and the exact main keyword is kept to about a quarter
        of the links to a target (but is used when it was never used and the target has 3 or more links)."""
        slug = target["planned_slug"]
        cands = anchor_candidates(target)
        ctx = self.words.get(source["planned_slug"], {}) if source else {}
        total = sum(self.anchor_use[f"{slug}|{c}"] for c in cands)
        main_uses = self.anchor_use[f"{slug}|{cands[0]}"]
        want_main = total >= 3 and main_uses * 4 < total

        def overlap(c: str) -> int:
            return sum(1 for t in word_counts([c]) if t in ctx)
        order = sorted(range(len(cands)), key=lambda i: (
            self.anchor_use[f"{slug}|{cands[i]}"],
            (i != 0) if want_main else (i == 0),  # main first only when it is owed, else secondary keywords first
            -overlap(cands[i]), i))
        market = target.get("market", "")
        for i in order:  # one text never points at two targets of the same market
            owner = self.anchor_owner.get((market, cands[i].lower()))
            if owner in (None, slug):
                self.anchor_owner[(market, cands[i].lower())] = slug
                self.anchor_use[f"{slug}|{cands[i]}"] += 1
                alts = [c for j, c in enumerate(cands) if j != i][:3]
                return cands[i], " | ".join(alts)
        return cands[0], ""

    def status(self, src: str, dst: str) -> str:
        if self.published is None:
            return "include_in_draft"
        sp, dp = src in self.published, dst in self.published
        if sp and dp:
            return "existing_verify_present"
        if sp and not dp:
            return "update_old_post_after_target_live"
        return "include_in_draft" if dp else "include_in_draft_target_not_live_yet"

    def add(self, src: str, dst: str, ltype: str, placement: str, priority: int, reason: str) -> None:
        if src == dst or src not in self.posts or dst not in self.posts or (src, dst) in self.links:
            return
        anchor, alts = self.pick_anchor(self.posts[dst], self.posts[src])
        if ltype == "contextual":
            self.ctx_in[dst] += 1
        self.links[(src, dst)] = {
            "source_slug": src, "source_keyword": self.posts[src]["primary_keyword"], "target_slug": dst,
            "target_main_keyword": self.posts[dst]["primary_keyword"],
            "link_type": ltype, "anchor": anchor, "anchor_alternatives": alts, "placement": placement,
            "priority": priority, "status": self.status(src, dst), "reason": reason}

    def inbound(self, slug: str) -> int:
        return sum(1 for (_, d) in self.links if d == slug)

    def outbound(self, slug: str) -> int:
        return sum(1 for (s, _) in self.links if s == slug)

    def related(self, post: dict, exclude: set[str]) -> list[dict]:
        """Return only posts that share at least one facet: never force links between unrelated posts."""
        cands = [p for s, p in self.posts.items()
                 if s not in exclude and p["market"] == post["market"] and self.shared(post, p) >= 1]
        cands.sort(key=lambda p: (-self.shared(post, p), -(p["role"] == "pillar"), -to_int(p["cluster_volume"])))
        return cands

    # -- build
    def need(self, slug: str) -> int:
        """Contextual links a post may still receive: more when its main keyword is above the site's reach."""
        return INBOUND_CONTEXTUAL.get(self.posts[slug].get("main_kd_fit", ""), 3) - self.ctx_in[slug]

    def value(self, p: dict) -> int:
        return to_int(p.get("priority_score")) or to_int(p.get("cluster_volume"))

    def section_of(self, target: dict) -> str:
        return f"the section on '{target['primary_keyword']}' (one H2 or paragraph)"

    def build(self) -> None:
        by_pillar: dict[str, list[dict]] = defaultdict(list)
        for p in self.posts.values():
            if p["pillar_id"]:
                by_pillar[p["pillar_id"]].append(p)
        for pid, members in by_pillar.items():
            pillar = self.pillar_slug.get(pid)  # None: the group has no real pillar yet, its posts link to each other
            clusters = [m for m in members if m["role"] == "cluster"]
            children: dict[str, list[dict]] = defaultdict(list)
            for c in clusters:
                if c.get("parent_post") in self.posts:
                    children[c["parent_post"]].append(c)
            for c in clusters:
                parent = c.get("parent_post") if c.get("parent_post") in self.posts else ""
                if pillar:
                    self.add(c["planned_slug"], pillar, "to_pillar", "intro: name the broader topic and link to the pillar", 1,
                             "every post links up to its pillar: the pillar targets the broad query and gathers the "
                             "cluster's authority")
                if parent:
                    self.add(c["planned_slug"], parent, "to_parent", "first H2: link to the guide this post narrows down", 1,
                             f"this post narrows down '{self.posts[parent]['primary_keyword']}' (its sub-hub)")
            for head, kids in children.items():
                for k in sorted(kids, key=lambda k: -self.value(k))[: self.pillar_links]:
                    self.add(head, k["planned_slug"], "from_parent", self.section_of(k), 1,
                             f"sub-hub links down to the posts on its subject ({len(kids)} posts)")
            if pillar:
                direct = [c for c in clusters if c.get("parent_post") not in self.posts]
                heads = [c for c in direct if c["planned_slug"] in children]
                rest = sorted((c for c in direct if c["planned_slug"] not in children), key=lambda c: -self.value(c))
                budget = max(0, self.pillar_links - len(heads))
                for c in heads:
                    self.add(pillar, c["planned_slug"], "from_pillar", self.section_of(c), 1,
                             f"pillar links down to its sub-hub '{c['primary_keyword']}' ({len(children[c['planned_slug']])} "
                             "posts below it)")
                for i, c in enumerate(rest):
                    if i < budget:
                        self.add(pillar, c["planned_slug"], "from_pillar", self.section_of(c), 1,
                                 "pillar links down to one of its most valuable posts")
                    else:
                        self.later.append((c["planned_slug"], f"not linked from the pillar (budget of {self.pillar_links} "
                                                              "body links): it gets contextual links instead"))
        self._contextual()
        for p in sorted(self.posts.values(), key=lambda p: -self.value(p)):
            if p["role"] == "standalone" and p["parent_hint"] in self.pillar_slug:
                pillar = self.pillar_slug[p["parent_hint"]]
                self.add(p["planned_slug"], pillar, "to_pillar", "intro or first H2 (first half of the post)", 1,
                         "standalone post links to the suggested pillar")
                down = sum(1 for (s, _), l in self.links.items() if s == pillar and l["link_type"] == "from_pillar")
                if down < self.pillar_links:  # the pillar's body budget holds its standalone guides too
                    self.add(pillar, p["planned_slug"], "from_pillar", "related-guides section", 2,
                             "pillar links to a related standalone guide")
                else:
                    self.later.append((p["planned_slug"], f"standalone guide not linked from the pillar (budget of "
                                                          f"{self.pillar_links} body links)"))
        for p in self.posts.values():
            if p["role"] == "skip":
                continue
            done = 0
            for f in ("interest", "recipient", "craft", "occasion", "product"):
                if done >= self.max_cross or not p.get(f):
                    continue
                pid = self.pillar_by_key.get((p["market"], p[f]))
                if pid and pid != p["pillar_id"] and self.topic(self.posts[self.pillar_slug[pid]]) != self.topic(p):
                    before = len(self.links)
                    self.add(p["planned_slug"], self.pillar_slug[pid], "cross_pillar", "body or related reading", 3,
                             f"shares facet '{f}={p[f]}' with another pillar")
                    done += len(self.links) - before
        self._fix_orphans_and_dead_ends()
        self._related_reading()
        self._backlink_queue()

    def _related_reading(self) -> None:
        """'Related reading' block (the Related Post column): the most similar posts of the same sub-hub, then of the
        same pillar, that the post does not already link to in its body."""
        for slug, p in self.posts.items():
            if p["role"] not in ("cluster", "standalone") or not p["pillar_id"]:
                continue
            mine = self.words.get(slug, {})
            sibs = [q for q in self.posts.values() if q["pillar_id"] == p["pillar_id"] and q["role"] == "cluster"
                    and q["planned_slug"] != slug and (slug, q["planned_slug"]) not in self.links]
            ranked = sorted(sibs, key=lambda q: (q.get("parent_post", "") != p.get("parent_post", "") or not p.get("parent_post"),
                                                 -cosine(mine, self.words.get(q["planned_slug"], {})), -self.value(q)))
            for q in ranked[: self.max_related]:
                sim = cosine(mine, self.words.get(q["planned_slug"], {}))
                same_hub = p.get("parent_post") and q.get("parent_post") == p.get("parent_post")
                self.add(slug, q["planned_slug"], "related_reading", "end of post: 'Related reading'", 3,
                         ("another post under the same sub-hub" if same_hub else "another post of the same pillar")
                         + (f" (similarity {sim:.2f})" if sim else ""))

    def topic(self, p: dict) -> str:
        return (p.get("pillar_key") or "").split("/", 1)[0]

    def _contextual(self) -> None:
        """Body links between posts that talk about the same thing, in any theme pillar of the topic: 'facts about the
        first thanksgiving' -> 'when was the first thanksgiving'. Up to max_contextual per post, never to its own
        pillar or sub-hub (already linked), never between unrelated posts (cosine of their keyword words >=
        CONTEXTUAL_MIN), and a target receives at most INBOUND_CONTEXTUAL of them by how hard its keyword is for the
        site: links go where they help a post rank. Posts in volume order, so the strongest choose first."""
        order = sorted(self.posts.items(), key=lambda kv: -self.value(kv[1]))
        for slug, p in order:
            if p["role"] not in ("cluster", "standalone"):
                continue
            mine = self.words.get(slug, {})
            own = {self.pillar_slug.get(p["pillar_id"]), p.get("parent_post")}
            scored = []
            for other, q in self.posts.items():
                if other in own or other == slug or q["market"] != p["market"] or (slug, other) in self.links:
                    continue
                if self.topic(q) != self.topic(p) or q["role"] == "pillar":
                    continue
                score = cosine(mine, self.words.get(other, {}))
                if score >= CONTEXTUAL_MIN:
                    scored.append((score, other))
            done = 0
            for score, other in sorted(scored, reverse=True):
                if done >= self.max_contextual:
                    break
                if self.need(other) <= 0:
                    continue
                shared = sorted(set(mine) & set(self.words.get(other, {})), key=lambda t: (-mine[t], t))[:3]
                fit = self.posts[other].get("main_kd_fit", "")
                self.add(slug, other, "contextual", f"the paragraph that mentions {', '.join(shared)}", 2,
                         f"related angle (shared words: {', '.join(shared)}; similarity {score:.2f})"
                         + (f"; the target's keyword is '{fit}' for the site, internal links help it rank"
                            if fit in ("stretch", "hard") else ""))
                done += 1

    def _fix_orphans_and_dead_ends(self) -> None:
        for slug, p in self.posts.items():
            if self.inbound(slug) == 0:
                for src in self.related(p, {slug}):
                    before = len(self.links)
                    self.add(src["planned_slug"], slug, "orphan_fix", "body, where the topic is relevant", 1,
                             "post would have no inbound internal link otherwise")
                    if len(self.links) > before:
                        break
                else:
                    self.unresolved.append((slug, "no inbound link and no post on the same topic to link from naturally"))
            if self.outbound(slug) == 0:
                for dst in self.related(p, {slug}):
                    before = len(self.links)
                    self.add(slug, dst["planned_slug"], "related", "body or end-of-post related reading", 2,
                             "post would have no outbound internal link otherwise")
                    if len(self.links) > before:
                        break
                else:
                    self.unresolved.append((slug, "no outbound link and no post on the same topic to link to naturally"))

    def _backlink_queue(self) -> None:
        if not self.published:
            return
        for slug, p in list(self.posts.items()):
            if slug in self.published:
                continue
            incoming_old = [s for (s, d) in self.links if d == slug and s in self.published]
            for src in self.related(p, {slug}):
                if len(incoming_old) >= 3:
                    break
                if src["planned_slug"] in self.published and src["planned_slug"] not in incoming_old:
                    before = len(self.links)
                    self.add(src["planned_slug"], slug, "backlink_old_post", "body, where the topic is relevant", 2,
                             "update an older published post to link to the new post")
                    if len(self.links) > before:
                        incoming_old.append(src["planned_slug"])


FIELDS = ["source_slug", "source_keyword", "target_slug", "target_main_keyword", "link_type", "anchor", "anchor_alternatives",
          "placement", "priority", "status", "reason"]


def run_plan(args) -> int:
    rows = read_csv(args.topic_map)
    published = None
    if args.published:
        published = {slug_of(r.get("slug") or r.get("url") or next(iter(r.values()), "")) for r in read_csv(args.published)}
    pl = Planner(rows, published, args.max_siblings, args.max_cross, args.max_contextual, args.pillar_links,
                 args.max_related)
    pl.build()
    links = sorted(pl.links.values(), key=lambda l: (l["priority"], l["source_slug"], l["target_slug"]))
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "link-plan.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(links)
    out_counts = defaultdict(int)
    for l in links:
        out_counts[l["source_slug"]] += 1
    warn = [f"- `{s}` has {n} outgoing links: check the density when writing (reference ~3-5 contextual links per 1,000 words)"
            for s, n in sorted(out_counts.items(), key=lambda kv: -kv[1])
            if n > (PILLAR_OUTBOUND_WARN if pl.posts[s]["role"] == "pillar" else OUTBOUND_REVIEW_MAX)]
    types = defaultdict(int)
    for l in links:
        types[l["link_type"]] += 1
    lines = ["# Internal link plan summary", "",
             f"- {len(pl.posts)} posts, {len(links)} proposed links", "- By type: " +
             ", ".join(f"{k}={v}" for k, v in sorted(types.items())),
             f"- Anchors that are the exact main keyword of the target: {sum(1 for l in links if l['anchor'].lower() == l['target_main_keyword'].lower())} of {len(links)} (the URL slug always follows the main keyword, the anchor may be a secondary keyword)",
             f"- Posts with no inbound link: {sum(1 for s in pl.posts if pl.inbound(s) == 0)}",
             f"- Posts with no outbound link: {sum(1 for s in pl.posts if pl.outbound(s) == 0)}", ""]
    if pl.later:
        lines += ["## Not linked from the pillar body", "",
                  f"The pillar links to its sub-hubs and its {pl.pillar_links} most valuable posts; these reach readers "
                  "through contextual links and the related-reading block:", ""]
        lines += [f"- `{s}`: {why}" for s, why in pl.later] + [""]
    if pl.unresolved:
        lines += ["## Not resolvable with natural links (content gap)", "",
                  "Links are not forced between unrelated posts. Add a post on the same topic or let the editor decide:", ""]
        lines += [f"- `{s}`: {why}" for s, why in pl.unresolved] + [""]
    if warn:
        lines += ["## Density to check", *warn, ""]
    lines += ["## Notes for writers", "- The target URL is built from the target's MAIN keyword; the anchor is chosen for the sentence it sits in and may be one of the target's secondary keywords.", "- Anchors are suggestions only: rewrite them to fit the sentence (2-8 words) and to describe the target page accurately.",
              "- Link to each target URL only once per post; put the 1-2 most important links in the first half of the post.",
              "- For UK posts use British spelling in anchors (mum, personalised)."]
    with open(os.path.join(args.out, "link-summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"{len(pl.posts)} posts -> {len(links)} proposed links | " + ", ".join(f"{k}={v}" for k, v in sorted(types.items())))
    print(f"Written to: {os.path.abspath(args.out)}")
    return 0


# --------------------------------------------------------------------------- audit
def col(row: dict, names: list[str]) -> str:
    low = {k.strip().lower(): v for k, v in row.items()}
    for n in names:
        if n in low:
            return low[n] or ""
    return ""


def run_audit(args) -> int:
    raw = read_csv(args.links)
    links = [(slug_of(col(r, ["source", "from", "source url", "from url"])),
              slug_of(col(r, ["target", "to", "destination", "target url", "to url"])),
              col(r, ["anchor", "anchor text", "link text", "text"]).strip()) for r in raw]
    links = [l for l in links if l[0] and l[1]]
    issues: list[tuple[str, str, str, str]] = []  # (severity, rule, where, detail)
    nodes = {s for s, _, _ in links} | {t for _, t, _ in links}
    pillars: dict[str, str] = {}
    members: dict[str, list[str]] = defaultdict(list)
    parent_of: dict[str, str] = {}
    if args.topic_map:
        for r in read_csv(args.topic_map):
            if r["role"] == "skip" or not r["planned_slug"]:
                continue
            nodes.add(r["planned_slug"])
            if r["role"] == "pillar":
                pillars[r["pillar_id"]] = r["planned_slug"]
            elif r["role"] == "cluster":
                members[r["pillar_id"]].append(r["planned_slug"])
                if r.get("parent_post"):
                    parent_of[r["planned_slug"]] = r["parent_post"]

    inbound, outbound, anchor_targets, pair_count = defaultdict(int), defaultdict(int), defaultdict(set), defaultdict(int)
    for s, t, a in links:
        inbound[t] += 1
        outbound[s] += 1
        pair_count[(s, t)] += 1
        if a:
            anchor_targets[a.lower()].add(t)
        n_words = len(a.split())
        if a.lower() in GENERIC_ANCHORS:
            issues.append(("high", "generic_anchor", f"{s} -> {t}", f"anchor chung chung: '{a}'"))
        elif not a:
            issues.append(("medium", "empty_anchor", f"{s} -> {t}", "empty anchor (for an image link the ALT text is the anchor)"))
        elif not re.match(r"^https?://", a) and (n_words < 2 or n_words > 8):
            issues.append(("low", "anchor_length", f"{s} -> {t}", f"anchor has {n_words} words: '{a}' (should be 2-8)"))
    for (s, t), n in pair_count.items():
        if n > 1:
            issues.append(("low", "duplicate_link", f"{s} -> {t}", f"{n} links to the same target in one post"))
    for a, targets in anchor_targets.items():
        if len(targets) > 1:
            issues.append(("medium", "anchor_reused", a, "same anchor used for several targets: " + ", ".join(sorted(targets))))
    for n in sorted(nodes):
        if inbound[n] == 0:
            issues.append(("high", "orphan", n, "no inbound internal link"))
        if outbound[n] == 0:
            issues.append(("medium", "dead_end", n, "no outbound internal link"))
        if inbound[n] > INBOUND_HEURISTIC_MAX:
            issues.append(("low", "many_inbound", n, f"{inbound[n]} inbound links (> ~{INBOUND_HEURISTIC_MAX}: Zyppy heuristic, review manually)"))
        if outbound[n] > OUTBOUND_REVIEW_MAX:
            issues.append(("low", "many_outbound", n, f"{outbound[n]} outbound links, check the density"))
    present = {(s, t) for s, t, _ in links}
    for pid, pslug in pillars.items():
        for c in members[pid]:
            if (c, pslug) not in present:
                issues.append(("high", "cluster_missing_pillar_link", c, f"does not link up to pillar {pslug}"))
            parent = parent_of.get(c)
            if (pslug, c) not in present and (not parent or (parent, c) not in present):
                # a post under a sub-hub is reached through it; a pillar need not list every post in its body
                where = f"neither pillar {pslug} nor its sub-hub {parent}" if parent else f"pillar {pslug}"
                sev = "high" if inbound[c] == 0 else "low"
                issues.append((sev, "pillar_missing_cluster_link", c, f"no link down from {where}"
                               + ("" if sev == "high" else f" ({inbound[c]} other inbound link(s))")))
    order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: (order[i[0]], i[1]))
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "link-audit.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["severity", "rule", "where", "detail"])
        w.writerows(issues)
    counts = defaultdict(int)
    for sev, rule, _, _ in issues:
        counts[(sev, rule)] += 1
    print(f"{len(links)} links, {len(nodes)} posts -> {len(issues)} issues")
    for (sev, rule), n in sorted(counts.items(), key=lambda kv: (order[kv[0][0]], kv[0][1])):
        print(f"  [{sev}] {rule}: {n}")
    print(f"Written to: {os.path.abspath(args.out)}")
    return 1 if any(i[0] == "high" for i in issues) else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="plan links from topic-map.csv")
    p.add_argument("topic_map")
    p.add_argument("--published", help="CSV of published posts (slug or url column)")
    p.add_argument("--max-siblings", type=int, default=3, help="kept for compatibility: see --max-related")
    p.add_argument("--max-cross", type=int, default=1)
    p.add_argument("--max-contextual", type=int, default=2,
                   help="body links per post to the most related posts of the same topic (default 2)")
    p.add_argument("--pillar-links", type=int, default=12,
                   help="body links from a pillar down to its sub-hubs and most valuable posts (default 12); the "
                        "posts under a sub-hub are linked from the sub-hub")
    p.add_argument("--max-related", type=int, default=3,
                   help="posts of the same sub-hub or pillar in the 'Related reading' block (default 3)")
    p.add_argument("--out", default="outputs")
    p.set_defaults(fn=run_plan)
    a = sub.add_parser("audit", help="audit an existing link file")
    a.add_argument("links")
    a.add_argument("--topic-map")
    a.add_argument("--out", default="outputs")
    a.set_defaults(fn=run_audit)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
