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
def anchor_candidates(row: dict) -> list[str]:
    main = clean_anchor(row["primary_keyword"])
    cands: list[str] = []
    for k in [main] + [clean_anchor(k) for k in row["keywords"].split("|") if k][:4]:
        if 2 <= len(k.split()) <= 8 and k.lower() not in {c.lower() for c in cands}:
            cands.append(k)
    if row["post_type"] == "pillar-hub":
        desc = f"our guide to {main}"
        if len(desc.split()) <= 8 and desc not in cands:
            cands.append(desc)
    return cands or [main]


class Planner:
    def __init__(self, rows: list[dict], published: set[str] | None, max_siblings: int, max_cross: int):
        self.posts = {r["planned_slug"]: r for r in rows if r["role"] != "skip" and r["planned_slug"]}
        self.published = published
        self.max_siblings, self.max_cross = max_siblings, max_cross
        self.links: dict[tuple[str, str], dict] = {}
        self.unresolved: list[tuple[str, str]] = []  # (slug, reason) posts with no natural place to link
        self.anchor_owner: dict[str, str] = {}
        self.anchor_use: dict[str, int] = defaultdict(int)
        self.pillar_slug = {r["pillar_id"]: r["planned_slug"] for r in self.posts.values() if r["role"] == "pillar"}
        self.pillar_by_key = {(r["market"], r["pillar_key"]): r["pillar_id"]
                              for r in self.posts.values() if r["role"] == "pillar"}

    # -- helpers
    def shared(self, a: dict, b: dict) -> int:
        return sum(1 for f in FACETS if a.get(f) and a.get(f) == b.get(f))

    def pick_anchor(self, target: dict) -> tuple[str, str]:
        slug = target["planned_slug"]
        cands = anchor_candidates(target)
        order = sorted(range(len(cands)), key=lambda i: (self.anchor_use[f"{slug}|{cands[i]}"], i))
        for i in order:
            owner = self.anchor_owner.get(cands[i].lower())
            if owner in (None, slug):
                self.anchor_owner[cands[i].lower()] = slug
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
        anchor, alts = self.pick_anchor(self.posts[dst])
        self.links[(src, dst)] = {
            "source_slug": src, "source_keyword": self.posts[src]["primary_keyword"], "target_slug": dst,
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
    def build(self) -> None:
        by_pillar: dict[str, list[dict]] = defaultdict(list)
        for p in self.posts.values():
            if p["pillar_id"]:
                by_pillar[p["pillar_id"]].append(p)
        for pid, members in by_pillar.items():
            pillar = self.pillar_slug[pid]
            clusters = [m for m in members if m["role"] == "cluster"]
            for c in clusters:
                self.add(c["planned_slug"], pillar, "to_pillar", "intro or first H2 (first half of the post)", 1,
                         "cluster links up to its pillar")
                self.add(pillar, c["planned_slug"], "from_pillar", "section that covers this angle", 1,
                         "pillar links down to every cluster")
            for c in clusters:
                sibs = sorted((s for s in clusters if s is not c),
                              key=lambda s: (-self.shared(c, s), -to_int(s["cluster_volume"])))
                for s in sibs[: self.max_siblings]:
                    self.add(c["planned_slug"], s["planned_slug"], "sibling", "body, where the angle is relevant", 2,
                             f"related angle in the same pillar (shared facets: {self.shared(c, s)})")
        for p in self.posts.values():
            if p["role"] == "standalone" and p["parent_hint"] in self.pillar_slug:
                pillar = self.pillar_slug[p["parent_hint"]]
                self.add(p["planned_slug"], pillar, "to_pillar", "intro or first H2 (first half of the post)", 1,
                         "standalone post links to the suggested pillar")
                self.add(pillar, p["planned_slug"], "from_pillar", "related-guides section", 2,
                         "pillar links to a related standalone guide")
        for p in self.posts.values():
            if p["role"] == "skip":
                continue
            done = 0
            for f in ("interest", "recipient", "craft", "occasion", "product"):
                if done >= self.max_cross or not p.get(f):
                    continue
                pid = self.pillar_by_key.get((p["market"], p[f]))
                if pid and pid != p["pillar_id"]:
                    before = len(self.links)
                    self.add(p["planned_slug"], self.pillar_slug[pid], "cross_pillar", "body or related reading", 3,
                             f"shares facet '{f}={p[f]}' with another pillar")
                    done += len(self.links) - before
        self._fix_orphans_and_dead_ends()
        self._backlink_queue()

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


FIELDS = ["source_slug", "source_keyword", "target_slug", "link_type", "anchor", "anchor_alternatives",
          "placement", "priority", "status", "reason"]


def run_plan(args) -> int:
    rows = read_csv(args.topic_map)
    published = None
    if args.published:
        published = {slug_of(r.get("slug") or r.get("url") or next(iter(r.values()), "")) for r in read_csv(args.published)}
    pl = Planner(rows, published, args.max_siblings, args.max_cross)
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
             f"- Posts with no inbound link: {sum(1 for s in pl.posts if pl.inbound(s) == 0)}",
             f"- Posts with no outbound link: {sum(1 for s in pl.posts if pl.outbound(s) == 0)}", ""]
    if pl.unresolved:
        lines += ["## Not resolvable with natural links (content gap)", "",
                  "Links are not forced between unrelated posts. Add a post on the same topic or let the editor decide:", ""]
        lines += [f"- `{s}`: {why}" for s, why in pl.unresolved] + [""]
    if warn:
        lines += ["## Density to check", *warn, ""]
    lines += ["## Notes for writers", "- Anchors are suggestions only: rewrite them to fit the sentence (2-8 words) and to describe the target page accurately.",
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
    if args.topic_map:
        for r in read_csv(args.topic_map):
            if r["role"] == "skip" or not r["planned_slug"]:
                continue
            nodes.add(r["planned_slug"])
            if r["role"] == "pillar":
                pillars[r["pillar_id"]] = r["planned_slug"]
            elif r["role"] == "cluster":
                members[r["pillar_id"]].append(r["planned_slug"])

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
            if (pslug, c) not in present:
                issues.append(("high", "pillar_missing_cluster_link", pslug, f"does not link down to cluster {c}"))
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
    p.add_argument("--max-siblings", type=int, default=3)
    p.add_argument("--max-cross", type=int, default=1)
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
