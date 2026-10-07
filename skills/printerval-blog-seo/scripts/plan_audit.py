#!/usr/bin/env python3
"""Sheets of the final plan that explain how the SEO's grouping was checked and why each link is there (module of
export_plan.py; standard library only).

  SEO Audit  one or more rows per group of the SEO's grouped file (keyword-clustering --prior, --prior-mode audit;
             Volume is the keyword's for a keyword check and the whole group's for a group check):
             what the rules changed (merged, section of another post, a better main keyword, a keyword moved or split
             out, the pillar...) or 'kept', the evidence, and where the group is now in the plan (STT). Built from
             seo-audit.csv (cluster step) and seo-audit-topic.csv (topic step); possible duplicates are listed for a
             SERP check, never applied.
  Link Plan  every planned link: from STT to STT, type, anchor, where it goes in the post, priority and reason
             (link-plan.csv of internal-link-planner), so the editor sees the logic behind each Internal Link cell.
"""
from __future__ import annotations

import re
from collections import defaultdict

AUDIT_COLUMNS = ["SEO STT", "SEO Main Keyword", "SEO Kind", "SEO Pillar", "Check", "Result", "Keyword", "Volume",
                 "Now in Plan (STT)", "Now Main Keyword", "Why", "Level"]
AUDIT_WIDTHS = [8, 40, 9, 32, 18, 16, 40, 9, 12, 40, 90, 13]
LINK_COLUMNS = ["From STT", "From Main Keyword", "To STT", "To Main Keyword", "Link Type", "Anchor", "Placement",
                "Priority", "Reason"]
LINK_WIDTHS = [8, 40, 7, 40, 15, 40, 44, 8, 80]
RESULT = {"merged": "merged", "section": "section", "main_changed": "main changed", "removed": "keyword moved",
          "split": "split out", "moved": "moved to pillar", "pillar_changed": "pillar changed",
          "check_serp": "check SERP", "kept": "kept (flagged)", "added": "added from export"}
CHECK_ORDER = {"pillar_changed": 0, "pillar_fit": 1, "same_query": 2, "same_subject": 3, "section": 4,
               "main_changed": 5, "duplicate": 6, "shop_member": 7, "possible_duplicate": 8, "noise_flag": 9,
               "export_topic": 10, "kept": 11}
LINK_ORDER = {"to_pillar": 0, "to_parent": 1, "from_pillar": 2, "from_parent": 3, "contextual": 4, "cross_pillar": 5,
              "orphan_fix": 6, "related": 7, "related_reading": 8, "backlink_old_post": 9}


def _key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _stt_num(v: str) -> tuple:
    try:
        return (0, float(v))
    except (TypeError, ValueError):
        return (1, v or "")


class Where:
    """Where a keyword or a cluster ended up in the plan: (STT, main keyword of that post) or (None, why not)."""

    def __init__(self, plan, topic: list[dict], keywords: list[dict] | None):
        self.plan = plan
        self.post_of_cluster: dict[str, str] = {}
        self.role: dict[str, str] = {}
        self.volume: dict[str, str] = {}
        for r in topic:
            cid = r.get("cluster_id", "")
            self.role[cid] = r.get("role", "")
            self.volume[cid] = r.get("cluster_volume", "")
            slug = r.get("planned_slug") or r.get("merged_into") or ""
            if slug:
                self.post_of_cluster[cid] = slug
        self.cluster_of_kw: dict[str, str] = {}
        self.cluster_of_group: dict[str, str] = {}
        for k in keywords or []:
            cid = k.get("cluster_id", "")
            for kw in [k.get("keyword", "")] + [v for v in (k.get("variants") or "").split("|") if v]:
                self.cluster_of_kw.setdefault(_key(kw), cid)
            if k.get("prior_group") and _key(k.get("keyword")) == _key(k.get("prior_main")):
                self.cluster_of_group.setdefault((k.get("market", ""), k["prior_group"]), cid)

    def of_cluster(self, cid: str) -> tuple[int | None, str]:
        slug = self.post_of_cluster.get(cid, "")
        if slug in self.plan.stt:
            post = next(p for p in self.plan.posts if p["planned_slug"] == slug)
            return self.plan.stt[slug], post["primary_keyword"]
        role = self.role.get(cid, "")
        return None, {"skip": "not in the blog plan: shopping intent (shop pages)",
                      "backlog": "backlog: not planned as a post"}.get(role, "not in the plan")

    def of_keyword(self, kw: str) -> tuple[int | None, str]:
        cid = self.cluster_of_kw.get(_key(kw))
        return self.of_cluster(cid) if cid else (None, "not in the plan (filtered: see excluded.csv)")


def seo_audit_rows(plan, topic: list[dict], keywords: list[dict] | None, audits: list[dict]) -> list[list]:
    """SEO Audit sheet rows: every audit row of both steps, then 'kept' for each SEO group no rule changed, in the
    SEO's own order (STT), so the sheet reads next to the SEO's file."""
    where = Where(plan, topic, keywords)
    out = []
    merged_away = {(a.get("market", ""), a.get("seo_group", "")) for a in audits
                   if a.get("check") in ("same_query", "same_subject", "section")}
    touched = merged_away | {(a.get("market", ""), a.get("seo_group", "")) for a in audits
                             if a.get("check") in ("pillar_fit", "pillar_changed", "main_changed")}
    for a in audits:
        check, action = a.get("check", ""), a.get("action", "")
        if check == "possible_duplicate" and (a.get("market", ""), a.get("seo_group", "")) in merged_away:
            continue  # settled: the group is already part of another post
        kw = a.get("keyword", "")
        n, now = where.of_keyword(kw) if kw else (None, "")
        if check == "export_topic":
            n, now = where.of_keyword(kw)
        out.append([a.get("seo_group", ""), a.get("seo_main", ""), a.get("seo_kind", ""), a.get("seo_pillar", ""),
                    check, RESULT.get(action, action), kw, a.get("keyword_volume", ""), n if n is not None else "",
                    now, a.get("evidence", ""), a.get("level", "")])
    seen = set()
    for k in keywords or []:
        g = (k.get("market", ""), k.get("prior_group", ""))
        if not g[1] or g in seen or _key(k.get("keyword")) != _key(k.get("prior_main")):
            continue
        seen.add(g)
        if g in touched:
            continue
        n, now = where.of_cluster(k.get("cluster_id", ""))
        group_volume = where.volume.get(k.get("cluster_id", ""), k.get("volume", ""))
        role = next((p["role"] for p in plan.posts if n is not None and plan.stt[p["planned_slug"]] == n), "")
        result = "kept as pillar" if role == "pillar" else "kept as post" if n is not None else "kept"
        out.append([g[1], k.get("prior_main", ""), "", k.get("prior_pillar", ""), "kept", result, k.get("keyword", ""),
                    group_volume, n if n is not None else "", now,
                    "no rule found anything against this group: it is planned as the SEO set it", "[Convention]"])
    out.sort(key=lambda r: (_stt_num(r[0]), CHECK_ORDER.get(r[4], 99)))
    return out


def audit_summary(rows: list[list]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r[5]] += 1
    order = ["kept as pillar", "kept as post", "merged", "section", "main changed", "moved to pillar", "pillar changed",
             "keyword moved", "split out", "check SERP", "kept (flagged)", "added from export"]
    return ", ".join(f"{k} {counts[k]}" for k in order if counts.get(k))


def link_plan_rows(plan, links: list[dict] | None) -> list[list]:
    out = []
    for l in links or []:
        src, dst = l.get("source_slug", ""), l.get("target_slug", "")
        if src not in plan.stt or dst not in plan.stt:
            continue
        out.append([plan.stt[src], l.get("source_keyword", ""), plan.stt[dst], l.get("target_main_keyword", ""),
                    l.get("link_type", ""), l.get("anchor", ""), l.get("placement", ""), l.get("priority", ""),
                    l.get("reason", "")])
    out.sort(key=lambda r: (r[0], LINK_ORDER.get(r[4], 99), r[2]))
    return out
