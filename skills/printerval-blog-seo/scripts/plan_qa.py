#!/usr/bin/env python3
"""Quality checks on the final plan before it goes to the content team. Standard library only.

Used by export_plan.py (QA sheet + summary); every check is an internal heuristic [Convention], a list for a person
to review, not a verdict:
  * overlap        two posts whose main keywords ask nearly the same thing (they would compete for one query)
  * misplaced      a keyword of one post that is exactly another post's main question
  * year_in_main   a main keyword with a year: a seasonal post keeps one URL and is refreshed every year
  * slug           duplicate (-2) or very long planned slugs
  * overloaded     a post that absorbs so many clusters that one outline cannot cover them
  * thin_links     a post with fewer than 2 internal links out, or no link in
  * weak_post      a post whose keywords add up to little volume: maybe a section of its pillar instead
  * hard_keyword   a very high KD main keyword: a long-term target, write it but do not expect quick traffic
"""
from __future__ import annotations

import re

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
QA_COLUMNS = ["Severity", "Check", "STT", "Main Keyword", "Detail", "Suggestion"]
QA_WIDTHS = [9, 13, 6, 40, 70, 60]
YEAR_RX = re.compile(r"\b(19|20)\d\d\b")
OVERLAP_JACCARD = 0.67
OVERLOADED_CLUSTERS = 100
QUESTION_WORDS = {"what", "when", "where", "why", "how", "who", "which"}
WEAK_POST_VOLUME = 500
HARD_KD = 70


def check(rows: list[dict], signature, light: set, merged_counts: dict, owned_volume: dict,
          inbound: dict) -> list[list]:
    """rows: the plan rows (n, post, kind, volume, kd, secondary, roles, internal, related, url).
    Returns QA rows [severity, check, STT, main keyword, detail, suggestion], most severe first."""
    issues: list[list] = []

    def add(sev, name, r, detail, suggestion):
        issues.append([sev, name, r["n"] if r else "", r["post"]["primary_keyword"] if r else "", detail, suggestion])

    # what a keyword asks: its words minus fillers and minus the topic word every post shares ('thanksgiving'); question
    # words stay, since 'who celebrates thanksgiving' and 'why do we celebrate thanksgiving' are different questions
    mains = [signature(r["post"]["primary_keyword"]) for r in rows]
    counts: dict[str, int] = {}
    for sig in mains:
        for t in sig:
            counts[t] = counts.get(t, 0) + 1
    drop = (set(light) - QUESTION_WORDS) | {t for t, n in counts.items() if n >= max(3, 0.5 * len(rows))}

    def asks(text: str) -> frozenset:
        return frozenset(signature(text) - drop)
    content = {r["n"]: asks(r["post"]["primary_keyword"]) for r in rows}
    by_main = {}
    for r in rows:
        if content[r["n"]] - QUESTION_WORDS:
            by_main.setdefault(content[r["n"]], r)
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            ca, cb = content[a["n"]], content[b["n"]]
            if a["post"]["market"] != b["post"]["market"] or not (ca - QUESTION_WORDS) or not (cb - QUESTION_WORDS):
                continue
            jac = len(ca & cb) / len(ca | cb)
            if jac >= OVERLAP_JACCARD:
                add("high", "overlap", b, f"asks nearly the same as STT {a['n']} '{a['post']['primary_keyword']}' "
                                          f"(shared words: {', '.join(sorted(ca & cb))})",
                    "merge the two posts, or give each a clearly different angle and say so in the outline")
    for r in rows:
        own = frozenset(content[r["n"]])
        for k, role in r["roles"]:
            if role not in ("secondary", "also covers"):
                continue
            other = by_main.get(asks(k["keyword"]))
            if other is not None and other is not r and frozenset(content[other["n"]]) != own:
                add("medium", "misplaced", r, f"'{k['keyword']}' is the main question of STT {other['n']} "
                                              f"'{other['post']['primary_keyword']}'",
                    f"answer it briefly here and link to STT {other['n']}, or move the keyword there")
        main = r["post"]["primary_keyword"]
        if YEAR_RX.search(main):
            add("medium", "year_in_main", r, f"main keyword contains a year: '{main}'",
                "use the evergreen form (no year) in the title and slug and refresh the post every year")
        slug = r["post"]["planned_slug"]
        if re.search(r"-\d+$", slug) and not YEAR_RX.search(slug):
            add("medium", "slug", r, f"slug '{slug}' was made unique with a number: another post has the same main keyword",
                "check for a duplicate post and rename one of them")
        elif len(slug) > 55:
            add("low", "slug", r, f"slug is long ({len(slug)} characters): '{slug}'", "shorten it to the core words")
        n_merged = merged_counts.get(slug, 0)
        if n_merged >= OVERLOADED_CLUSTERS:
            add("low", "overloaded", r, f"covers {n_merged} merged clusters (see the Keyword Map)",
                "check the outline can answer the biggest ones; split out a sub-topic if one keeps coming back")
        if len(r["internal"]) < 2 and r["kind"] == "Cluster":
            add("low", "thin_links", r, f"{len(r['internal'])} internal link(s) out", "add a link to a related post in the body")
        if inbound.get(slug, 0) == 0:
            add("high", "thin_links", r, "no other post links to it (orphan)", "link to it from its pillar and a related post")
        vol = owned_volume.get(slug, 0)
        if r["kind"] == "Cluster" and vol < WEAK_POST_VOLUME:
            add("low", "weak_post", r, f"all its keywords add up to {vol:,} searches a month",
                "keep it only if it serves a real reader need or fits a product well; else make it a section of the pillar")
        if r["kd"] is not None and r["kd"] >= HARD_KD:
            add("info", "hard_keyword", r, f"KD {r['kd']}: strong competition for the main keyword",
                "a long-term target: publish early, refresh yearly, win the long tail first")
    issues.sort(key=lambda i: (SEVERITY_ORDER[i[0]], i[1], i[2] if isinstance(i[2], int) else 0))
    return issues


def summary(issues: list[list]) -> str:
    counts: dict[tuple[str, str], int] = {}
    for sev, name, *_ in issues:
        counts[(sev, name)] = counts.get((sev, name), 0) + 1
    if not counts:
        return "QA: no issues found."
    parts = [f"{name} {n} ({sev})" for (sev, name), n in sorted(counts.items(), key=lambda kv: (SEVERITY_ORDER[kv[0][0]], kv[0][1]))]
    return f"QA: {len(issues)} items to review: " + ", ".join(parts)
