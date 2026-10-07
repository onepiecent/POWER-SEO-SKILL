"""Back-check a keyword grouping: the SEO's groups (prior mode) or the engine's own clusters (raw mode).

Every issue rests on evidence from the data (shared SERP URLs, the tool's Parent Topic, tool intent labels, volumes,
the need-vs-intent conflict) with the real numbers in one sentence, and proposes one decision in the decisions-file
columns. Nothing proposed here is applied: the reviewer (Claude or the SEO) copies a proposal into the decisions file
with a reason and evidence of their own.

backcheck() is a pure function of the rows cluster_keywords.build_rows produces (keyword-map rows as dicts or as
lists in KW_FIELDS order, cluster rows as dicts) plus an optional SERP URL map; write_backcheck() writes
backcheck.csv, proposed-decisions.csv and backcheck-report.md. Not a CLI: cluster_keywords.py calls it.

The group of a keyword is its prior_group, else its cluster's prior_group, else its cluster_id; the group's main is
the SEO's prior_main when set, else the cluster's cluster_name. Thresholds: SERP overlap = --serp-overlap, word
overlap = --sim; the other numbers below are [Convention] and printed in the report.
"""
import csv
import hashlib
import math
import os
import unicodedata
from collections import Counter, defaultdict

BACKCHECK_FIELDS = ["issue_id", "check", "severity", "market", "group", "group_main", "keyword", "keyword_volume",
                    "other_group", "other_main", "evidence_type", "evidence", "proposed_action", "proposed_keyword",
                    "proposed_target", "proposed_value", "status"]
DECISION_FIELDS = ["decision_id", "action", "market", "keyword", "target", "value", "reason", "evidence",
                   "source_issue", "author", "date"]
SEVERITIES = ("high", "medium", "low", "info")
LEX_FLOOR = 0.34          # word overlap with the own main below this is weak (the engine's MERGE_LEX_FLOOR) [Convention]
MIXED_SHARE = 0.2         # the smaller intent side holds >= 20% of the group's volume [Convention]
MAIN_RATIO = 2            # a member with >= 2x the main's volume would name the post better [Convention]
REPORT_ROWS = 300         # issues listed in backcheck-report.md; backcheck.csv has them all
CHECK_TEXT = {
    "duplicate_across_groups": "The same keyword is in two or more groups, so two posts would target it.",
    "secondary_is_other_main": "A secondary keyword of this group is, or answers the same query as, another group's "
                               "main keyword, so the two posts would compete.",
    "same_question_groups": "The main keywords of two groups are answered by the same results, so the two posts "
                            "would compete.",
    "weak_member": "A member fits another group's main better than its own main.",
    "mixed_intent": "The tool's intent labels split this group between readers who research and readers who buy.",
    "ungrouped_high_volume": "Keywords that are in no SEO group form a new cluster as big as an SEO group's main; "
                             "by default it stays a new post.",
    "main_not_best": "A member has much more search volume than the group's main keyword.",
    "no_data": "No keyword of this group has search volume in the exports.",
    "need_conflict": "The keyword's words say shop but the tool or the SERP says the reader researches; by default "
                     "it stays in the blog with the need shown.",
    "shopping_main": "The group's main keyword is a shopping query, so the topic map leaves the whole group to the "
                     "shop pages, including members that readers research.",
}
FACETS = ("occasion", "recipient", "interest", "product")  # a move or merge needs the same values (a different post)
QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'", "\u2032": "'",
                        "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u2033": '"'})
NEEDED = ("cluster_id", "market", "keyword", "volume", "variant_volumes", "parent_topic", "normalized_keyword",
          "reader_need", "need_source", "prior_group", "prior_main", "prior_role", "intents", "blog_fit",
          "serp_features") + FACETS


def decision_key(text) -> str:
    """The decisions-file matching key (contract C1): NFC, lowercase, straight quotes, apostrophes removed, '-' and
    '_' as spaces, whitespace collapsed."""
    s = unicodedata.normalize("NFC", str(text or "")).lower().translate(QUOTES)
    return " ".join(s.replace("'", "").replace("-", " ").replace("_", " ").split())


def issue_id(check: str, market: str, keyword: str, other_main: str) -> str:
    raw = f"{check}|{market}|{decision_key(keyword)}|{decision_key(other_main)}"
    return "BC-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


def _num(v) -> int:
    s = str("" if v is None else v).replace(",", "").strip()
    try:
        return int(float(s)) if s else 0
    except ValueError:
        return 0


class Kw:
    __slots__ = ("keyword", "key", "market", "volume", "cid", "parent", "norm", "toks", "need", "need_src", "intents",
                 "urls", "prior_group", "prior_main", "prior_role", "fit", "feats", "facets")


class Group:
    __slots__ = ("market", "name", "main", "key", "row", "members", "volume", "prior", "basis", "urls", "parent",
                 "norm", "toks", "mvol", "fit", "facets")


def _load(kw_rows, kw_fields, serp_urls) -> list[Kw]:
    idx = {f: i for i, f in enumerate(kw_fields or ())}
    out = []
    for row in kw_rows:
        if not isinstance(row, dict):
            row = {f: row[idx[f]] for f in NEEDED if f in idx}
        k = Kw()
        k.keyword = str(row.get("keyword") or "")
        k.key, k.market = decision_key(k.keyword), str(row.get("market") or "")
        k.volume = _num(row.get("volume")) + sum(_num(v) for v in str(row.get("variant_volumes") or "").split("|"))
        k.cid, k.parent = str(row.get("cluster_id") or ""), str(row.get("parent_topic") or "")
        k.norm = str(row.get("normalized_keyword") or "")
        k.toks = frozenset(k.norm.split() or k.key.split())
        k.need, k.need_src = str(row.get("reader_need") or ""), str(row.get("need_source") or "")
        k.intents = frozenset(t for t in str(row.get("intents") or "").split("|") if t)
        k.urls = frozenset(serp_urls.get((k.market, k.keyword)) or serp_urls.get(k.keyword) or ())
        k.prior_group, k.prior_main = str(row.get("prior_group") or ""), str(row.get("prior_main") or "")
        k.prior_role, k.fit = str(row.get("prior_role") or ""), str(row.get("blog_fit") or "")
        k.feats = str(row.get("serp_features") or "").replace("|", ", ")
        k.facets = tuple(str(row.get(f) or "") for f in FACETS)
        out.append(k)
    return out


def _groups(kws: list[Kw], cl_by_id: dict) -> list[Group]:
    by: dict[tuple, Group] = {}
    cids: dict[tuple, Counter] = defaultdict(Counter)
    for k in kws:
        cl_prior = str(cl_by_id.get(k.cid, {}).get("prior_group") or "")
        name = k.prior_group or cl_prior or k.cid
        g = by.get((k.market, name))
        if g is None:
            g = by[(k.market, name)] = Group()
            g.market, g.name, g.members, g.prior = k.market, name, [], bool(k.prior_group or cl_prior)
        g.members.append(k)
        cids[(k.market, name)][k.cid] += 1
    for gk, g in by.items():
        mains = [k.prior_main for k in g.members if k.prior_main]
        cid = cids[gk].most_common(1)[0][0]
        cl = cl_by_id.get(cid, {})
        g.main = mains[0] if mains else str(cl.get("cluster_name") or max(g.members, key=lambda k: k.volume).keyword)
        g.basis = "" if g.prior else str(cl.get("seed_basis") or "")
        g.key = decision_key(g.main)
        g.row = next((k for k in g.members if k.key == g.key), None)
        g.volume = sum(k.volume for k in g.members)
        g.urls = g.row.urls if g.row else frozenset()
        g.parent = decision_key(g.row.parent) if g.row else ""
        g.norm = g.row.norm if g.row else ""
        g.toks = g.row.toks if g.row else frozenset(g.key.split())
        g.mvol = g.row.volume if g.row else 0
        g.fit = g.row.fit if g.row else ""
        g.facets = g.row.facets if g.row else ()
    return sorted(by.values(), key=lambda g: (g.market, -g.volume, g.key, g.name))


def _jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _merge_order(g: Group, h: Group) -> tuple[Group, Group]:
    """(survivor, absorbed): the group with the bigger main survives."""
    a, b = sorted((g, h), key=lambda x: (-x.mvol, -x.volume, x.key, x.name))
    return a, b


def _same_post_kind(a: tuple, b: tuple) -> bool:
    """A keyword may only move to (or merge with) a group about the same occasion, recipient, interest and product:
    'christmas gifts for coworkers' never joins 'christmas gifts for mom', whatever the shared words."""
    return not a or not b or all(x == y for x, y in zip(a, b))


def _check(kw_rows, cl_rows, serp_urls=None, serp_t: int = 4, sim_t: float = 0.6, kw_fields=None, decided=None,
           also_in=None):
    kws = _load(kw_rows, kw_fields, serp_urls or {})
    cl_by_id = {str(c.get("cluster_id") or ""): c for c in cl_rows}
    groups = _groups(kws, cl_by_id)
    name_idx = {(g.market, g.name): i for i, g in enumerate(groups)}
    gi_of = {id(g): i for i, g in enumerate(groups)}
    url_idx, parent_idx, norm_idx, key_idx, tok_idx = (defaultdict(list) for _ in range(5))
    tok_df: Counter = Counter()
    for i, g in enumerate(groups):
        for u in g.urls:
            url_idx[(g.market, u)].append(i)
        if g.parent:
            parent_idx[(g.market, g.parent)].append(i)
        if g.norm:
            norm_idx[(g.market, g.norm)].append(i)
        key_idx[(g.market, g.key)].append(i)
        for t in g.toks:
            tok_idx[(g.market, t)].append(i)
            tok_df[(g.market, t)] += 1
    issues: list[dict] = []

    def issue(check, sev, g, keyword, kvol, other, etype, evidence, action, pk="", pt="", pv="", status="open"):
        issues.append({"issue_id": issue_id(check, g.market, keyword, other.main if other else ""), "check": check,
                       "severity": sev, "market": g.market, "group": g.name, "group_main": g.main, "keyword": keyword,
                       "keyword_volume": kvol, "other_group": other.name if other else "",
                       "other_main": other.main if other else "", "evidence_type": etype, "evidence": evidence,
                       "proposed_action": action, "proposed_keyword": pk, "proposed_target": pt, "proposed_value": pv,
                       "status": status})
        return issues[-1]

    def serp_best(urls, market, exclude, allowed=None):
        hits: Counter = Counter()
        for u in urls:
            hits.update(i for i in url_idx.get((market, u), ()) if i != exclude and (allowed is None or allowed(i)))
        return min(hits.items(), key=lambda x: (-x[1], x[0])) if hits else (None, 0)

    def lex_best(toks, market, exclude, allowed=None):
        """Best main by word overlap >= --sim; prefix filter: a main that reaches the threshold shares one of the
        len - ceil(t*len) + 1 rarest words of the keyword."""
        if not toks:
            return None, 0.0
        rare = sorted(toks, key=lambda t: (tok_df[(market, t)], t))
        cands = {i for t in rare[:max(1, len(rare) - math.ceil(sim_t * len(rare) - 1e-9) + 1)]
                 for i in tok_idx.get((market, t), ()) if i != exclude and (allowed is None or allowed(i))}
        scored = [(-_jaccard(toks, groups[i].toks), i) for i in cands]
        best = min(scored) if scored else (0.0, None)
        return (best[1], -best[0]) if -best[0] >= sim_t else (None, 0.0)

    # duplicate_across_groups: the same keyword (decisions key) in two or more groups of a market
    by_key: dict[tuple, dict] = defaultdict(dict)
    for i, g in enumerate(groups):
        for k in g.members:
            by_key[(g.market, k.key)].setdefault(i, k)
    # the grouped file listed a keyword in several groups; it was kept in one, the others are named in also_in
    for (market, key), names in (also_in or {}).items():
        hit = next(iter(by_key.get((market, key), {}).values()), None)
        for name in names:
            j = name_idx.get((market, name))
            if hit is not None and j is not None:
                by_key[(market, key)].setdefault(j, hit)
    for (market, key), hits in by_key.items():
        if len(hits) < 2:
            continue
        k0 = max(hits.values(), key=lambda k: (k.volume, len(k.urls)))
        urls = frozenset().union(*(k.urls for k in hits.values()))
        parent = decision_key(next((k.parent for k in hits.values() if k.parent), ""))

        def rank(i):
            """The group that names it as its main (in the SEO's file) keeps it; else the group whose OTHER members
            share most SERP URLs with it, then its Parent Topic, then the most shared words with those members."""
            g = groups[i]
            main = g.key == key and (not g.prior or any(m.key == key and m.prior_role == "main" for m in g.members))
            rest = [m for m in g.members if m.key != key]
            shared = max((len(urls & m.urls) for m in rest), default=0) if urls else 0
            words = max((_jaccard(k0.toks, m.toks) for m in rest), default=0.0)
            return (int(main), 0 if main else shared, int(bool(parent) and parent == g.key), round(words, 2), g.volume)
        order = sorted(hits, key=lambda i: (tuple(-x for x in rank(i)), i))
        win = groups[order[0]]
        tied = rank(order[0])[:4] == rank(order[1])[:4]
        parts = []
        for i in order:
            g = groups[i]
            ev = [f"main '{g.main}'"]
            if g.key == key:
                ev.append("it is the main")
            elif urls and g.urls:
                ev.append(f"{len(urls & g.urls)} shared SERP URLs with it")
            else:
                ev.append(f"word overlap with its other keywords {rank(i)[3]:.2f}")
            parts.append(f"'{g.name}' ({', '.join(ev)})")
        top = rank(order[0])
        why = ("tied on the evidence; the bigger group is proposed" if tied else "it is that group's main" if top[0]
               else "most SERP URLs shared with its other keywords" if top[1] else "its Parent Topic is that group's main"
               if top[2] else f"most shared words with its other keywords ({top[3]:.2f}; not verified by SERP)")
        etype = "lexical" if top[0] or not (top[1] or top[2]) else "serp" if top[1] else "parent_topic"
        target = win.main
        if win.key == key:  # the keyword is the winner's main: name the winning post by another of its members
            other = sorted((k for k in win.members if k.key != key), key=lambda k: (-k.volume, k.key))
            target = other[0].keyword if other else win.main
        now = k0.prior_group or ""
        it = issue("duplicate_across_groups", "high", groups[order[1]], k0.keyword, k0.volume, win, etype,
                   f"'{k0.keyword}' ({k0.volume:,} searches/month) is in {len(hits)} groups: " + "; ".join(parts) +
                   f". Keep it in '{win.name}': {why}." + (f" The script kept it in '{now}' (first in the file)."
                                                          if now else ""), "move_keyword", k0.keyword, target,
                   status="applied_default" if now == win.name else "open")
        it["group"] = "|".join(groups[i].name for i in order[1:])
        it["group_main"] = "|".join(groups[i].main for i in order[1:])
    dup_keys = {mk for mk, hits in by_key.items() if len(hits) > 1}

    for i, g in enumerate(groups):
        n_members = len(g.members)
        for k in g.members:
            if k.key == g.key:
                continue
            own = len(k.urls & g.urls) if k.urls and g.urls else None
            dup = (g.market, k.key) in dup_keys  # already reported by duplicate_across_groups
            # secondary_is_other_main: SERP (own main agrees or has no URLs), Parent Topic, same words
            found = None
            if k.urls and not dup and (own is None or own >= serp_t):
                j, n = serp_best(k.urls, g.market, i)
                if j is not None and n >= serp_t:
                    h = groups[j]
                    own_txt = "has no SERP URLs" if own is None else f"shares {own}"
                    found = (h, "serp", "high", f"'{k.keyword}' ({k.volume:,} searches/month) shares {n} of its "
                             f"{len(k.urls)} SERP URLs with '{h.main}', the main of group '{h.name}' (threshold "
                             f"{serp_t}); its own main '{g.main}' {own_txt}")
            if found is None and k.parent and not dup:
                pk = decision_key(k.parent)
                js = [j for j in key_idx.get((g.market, pk), ()) if j != i]
                if js and pk not in (g.key, k.key):  # a Parent Topic equal to the keyword itself says nothing
                    h = groups[js[0]]
                    found = (h, "parent_topic", "high", f"The Parent Topic of '{k.keyword}' ({k.volume:,} "
                             f"searches/month) is '{k.parent}', the main of group '{h.name}' ({h.mvol:,})")
            if found is None and not dup:
                js = [j for j in key_idx.get((g.market, k.key), ()) if j != i]
                js += [j for j in norm_idx.get((g.market, k.norm), ()) if j != i and k.norm and k.norm != g.norm]
                if js:
                    h = groups[js[0]]
                    found = (h, "lexical", "medium", f"'{k.keyword}' ({k.volume:,} searches/month) has the same "
                             f"words as '{h.main}', the main of group '{h.name}' ({h.mvol:,}), normalised "
                             f"'{k.norm or k.key}'")
            if found:
                h, etype, sev, ev = found
                a, b = _merge_order(g, h)
                issue("secondary_is_other_main", sev, g, k.keyword, k.volume, h, etype,
                      ev + f". Merge into '{a.main}' (main volume {a.mvol:,} vs {b.mvol:,}).", "merge", a.main, b.main)
            # weak_member: SERP overlap with the own main below the threshold while another main meets it
            elif not dup and own is not None and own < serp_t:
                j, n = serp_best(k.urls, g.market, i)
                if j is not None and n >= serp_t:
                    h = groups[j]
                    issue("weak_member", "high", g, k.keyword, k.volume, h, "serp",
                          f"SERP overlap of '{k.keyword}' ({k.volume:,} searches/month) with its own main '{g.main}' "
                          f"{own}/{len(k.urls)}, with '{h.main}' {n}/{len(k.urls)} (threshold {serp_t})",
                          "move_keyword", k.keyword, h.main)
            elif not dup and own is None and not (k.parent and decision_key(k.parent) in {g.key, g.parent}):
                own_j = _jaccard(k.toks, g.toks)
                if own_j < LEX_FLOOR:
                    j, s = lex_best(k.toks, g.market, i, lambda x: _same_post_kind(k.facets, groups[x].facets))
                    if j is not None:
                        h = groups[j]
                        issue("weak_member", "medium", g, k.keyword, k.volume, h, "lexical",
                              f"Word overlap of '{k.keyword}' ({k.volume:,} searches/month) with its own main "
                              f"'{g.main}' {own_j:.2f} (below {LEX_FLOOR}), with '{h.main}' {s:.2f} (threshold "
                              f"{sim_t}); no SERP URLs to compare, not verified by SERP", "move_keyword", k.keyword,
                              h.main)
                    elif not _same_post_kind(k.facets, g.facets):  # about another recipient, product...
                        diff = [f"{f} '{a or '-'}' vs '{b or '-'}'" for f, a, b in zip(FACETS, k.facets, g.facets)
                                if a != b]
                        issue("weak_member", "medium", g, k.keyword, k.volume, None, "lexical",
                              f"Word overlap of '{k.keyword}' ({k.volume:,} searches/month) with its own main "
                              f"'{g.main}' ({g.mvol:,}) is {own_j:.2f} (below {LEX_FLOOR}) and it is about something "
                              f"else ({', '.join(diff)}); no other group fits it, so it may be a post of its own (not "
                              "verified by SERP)", "split", k.keyword)
                    elif g.prior and k.volume >= g.mvol / 2:  # an SEO group, same subject in other words: SERP decides
                        issue("weak_member", "low", g, k.keyword, k.volume, None, "lexical",
                              f"Word overlap of '{k.keyword}' ({k.volume:,} searches/month) with its own main "
                              f"'{g.main}' ({g.mvol:,}) is only {own_j:.2f} (below {LEX_FLOOR}) but it is about the "
                              "same subject; check on the live SERP whether one page answers both (serp-check.csv)", "")
            # need_conflict: the words say shop, the tool or the SERP says the reader researches (M2)
            if k.need_src.startswith("conflict"):
                issue("need_conflict", "medium", g, k.keyword, k.volume, None,
                      "serp_features" if "serp features" in k.need_src.lower() else "tool_intent",
                      f"'{k.keyword}' ({k.volume:,} searches/month): {k.need_src.split(':', 1)[-1].strip()}; kept in "
                      f"the blog as '{k.need}' by default", "set_need", k.keyword, "", k.need, "applied_default")
        if g.row is not None and g.row.need_src.startswith("conflict"):
            k = g.row
            issue("need_conflict", "medium", g, k.keyword, k.volume, None,
                  "serp_features" if "serp features" in k.need_src.lower() else "tool_intent",
                  f"'{k.keyword}' ({k.volume:,} searches/month): {k.need_src.split(':', 1)[-1].strip()}; kept in the "
                  f"blog as '{k.need}' by default", "set_need", k.keyword, "", k.need, "applied_default")
        if n_members < 2:
            if g.volume == 0:
                issue("no_data", "medium" if g.prior else "low", g, g.main, 0, None, "data_missing",
                      f"'{g.main}' has volume 0 or no volume in the exports", "research_seed", g.main, "", g.main)
            continue
        # shopping_main: a shopping main takes the whole group out of the blog plan; keep the research side
        research = [k for k in g.members if k is not g.row and k.fit in ("high", "medium") and k.need != "shop"]
        if g.row is not None and g.fit == "low" and research:
            research.sort(key=lambda k: (-k.volume, k.key))
            rv = sum(k.volume for k in research)
            tool = f"tool intent {'/'.join(sorted(g.row.intents))}" if g.row.intents else "no tool intent"
            feats = f", SERP features {g.row.feats}" if g.row.feats else ""
            issue("shopping_main", "high", g, g.main, g.volume, None, "tool_intent" if g.row.intents else "lexical",
                  f"Main '{g.main}' ({g.mvol:,} searches/month) reads as a shopping query ({tool}{feats}); "
                  f"{len(research)} member(s) readers research ({rv:,} searches/month, led by '{research[0].keyword}' "
                  f"{research[0].volume:,}) would leave the blog with it. Split them into their own post",
                  "split", research[0].keyword, "", "|".join(k.keyword for k in research[1:]))
        # mixed_intent: informational-only members next to transactional-only ones
        info = [k for k in g.members if k.intents and k.intents <= {"informational"}]
        trans = [k for k in g.members if k.intents and k.intents <= {"transactional"}]
        if info and trans and g.volume:
            vi, vt = sum(k.volume for k in info), sum(k.volume for k in trans)
            side = trans if g.row in info else info if g.row in trans else (trans if vt <= vi else info)
            share = min(vi, vt) / g.volume
            if share >= MIXED_SHARE:
                side = sorted(side, key=lambda k: (-k.volume, k.key))
                issue("mixed_intent", "medium", g, g.main, g.volume, None, "tool_intent",
                      f"Tool intent: informational only ({len(info)} kw, {vi:,}) vs transactional only ({len(trans)} kw, "
                      f"{vt:,}); the smaller side is {share:.0%} of the group's {g.volume:,} (threshold "
                      f"{MIXED_SHARE:.0%})", "split", side[0].keyword, "", "|".join(k.keyword for k in side[1:]))
        # main_not_best: a member with >= 2x the main's volume
        others = sorted((k for k in g.members if k is not g.row), key=lambda k: (-k.volume, k.key))
        if others and others[0].volume > 0 and others[0].volume >= MAIN_RATIO * g.mvol:
            best = others[0]
            chosen = g.basis not in ("", "max_volume")
            main_txt = f"{g.mvol:,}" if g.row else "0, not in the data"
            issue("main_not_best", "low" if chosen else "medium", g, best.keyword, best.volume, None, "volume",
                  f"'{best.keyword}' has {best.volume:,} searches/month, " +
                  (f"{best.volume / g.mvol:.1f}x" if g.mvol else "more than") +
                  f" the main '{g.main}' ({main_txt}; threshold {MAIN_RATIO}x)" +
                  (f"; the engine chose the main on purpose: {g.basis}" if chosen else ""),
                  "rename_main", best.keyword)
        # no_data: no member has volume
        if g.volume == 0:
            issue("no_data", "medium" if g.prior else "low", g, g.main, 0, None, "data_missing",
                  f"None of the group's {n_members} keywords has search volume in the exports (all 0 or empty)",
                  "research_seed", g.main, "", "|".join(k.keyword for k in g.members[:30]))

    # same_question_groups: two mains with SERP overlap >= threshold, the same Parent Topic or the same words
    seen: set = set()
    for i, g in enumerate(groups):
        pairs = []
        if g.urls:
            hits: Counter = Counter()
            for u in g.urls:
                hits.update(j for j in url_idx.get((g.market, u), ()) if j > i)
            pairs += [(j, "serp", "high", f"share {n} SERP URLs (threshold {serp_t})")
                      for j, n in sorted(hits.items()) if n >= serp_t]
        if g.parent:
            pairs += [(j, "parent_topic", "high", f"have the same Parent Topic '{g.row.parent}'")
                      for j in parent_idx.get((g.market, g.parent), ()) if j > i]
            pairs += [(j, "parent_topic", "high", f"are one topic: the Parent Topic of '{g.main}' is '{g.row.parent}'")
                      for j in key_idx.get((g.market, g.parent), ()) if j != i]
        for j in parent_idx.get((g.market, g.key), ()):
            if j != i:
                pairs.append((j, "parent_topic", "high",
                              f"are one topic: the Parent Topic of '{groups[j].main}' is '{groups[j].row.parent}'"))
        if g.norm:
            pairs += [(j, "lexical", "medium", f"have the same words after normalising ('{g.norm}')")
                      for j in norm_idx.get((g.market, g.norm), ()) if j > i]
        for j, etype, sev, why in pairs:
            if (min(i, j), max(i, j)) in seen:
                continue
            seen.add((min(i, j), max(i, j)))
            a, b = _merge_order(g, groups[j])
            issue("same_question_groups", sev, a, a.main, a.volume + b.volume, b, etype,
                  f"Mains '{a.main}' ({a.mvol:,} searches/month, group {a.volume:,}) and '{b.main}' ({b.mvol:,}, group "
                  f"{b.volume:,}) {why}", "merge", a.main, b.main)

    # ungrouped_high_volume (prior mode only): a new cluster as big as the smallest SEO group main of its market
    seo = [i for i, g in enumerate(groups) if g.prior]
    if seo:
        floor: dict[str, int] = {}
        for i in seo:
            g = groups[i]
            if g.mvol > 0:
                floor[g.market] = min(floor.get(g.market, g.mvol), g.mvol)
        prior_set = set(seo)
        for i, g in enumerate(groups):
            thr = floor.get(g.market)
            if g.prior or thr is None or g.volume < thr:
                continue
            ev = (f"'{g.main}' ({len(g.members)} kw, {g.volume:,} searches/month) is in no SEO group; the smallest SEO "
                  f"group main in {g.market.upper() or 'this market'} has {thr:,}")
            if g.fit == "low":
                tool = f"tool intent {'/'.join(sorted(g.row.intents))}" if g.row and g.row.intents else "no tool intent"
                issue("ungrouped_high_volume", "info", g, g.main, g.volume, None, "tool_intent", ev + f"; it reads as a "
                      f"shopping query ({tool}{', SERP features ' + g.row.feats if g.row and g.row.feats else ''}), so "
                      "it is left to the shop pages, not the blog", "", status="applied_default")
                continue

            def fits(x):
                return x in prior_set and groups[x].fit != "low" and _same_post_kind(g.facets, groups[x].facets)
            j, n = serp_best(g.urls, g.market, i, fits)
            near, how = (j, f"{n} shared SERP URLs") if j is not None and n >= serp_t else (None, "")
            if near is None:
                j, s = lex_best(g.toks, g.market, i, fits)
                near, how = (j, f"word overlap {s:.2f}") if j is not None else (None, "")
            if near is None:
                issue("ungrouped_high_volume", "medium", g, g.main, g.volume, None, "volume",
                      ev + "; no SEO group main is close (SERP or words), so it stays a new post", "keep_keyword",
                      g.main, status="applied_default")
            else:
                h = groups[near]
                action = "merge" if len(g.members) > 1 else "move_keyword"
                pk, pt = (h.main, g.main) if action == "merge" else (g.main, h.main)
                issue("ungrouped_high_volume", "medium", g, g.main, g.volume, h, "volume",
                      ev + f"; nearest SEO group '{h.name}' (main '{h.main}', {how}); it stays a new post until "
                      f"decided", action, pk, pt, status="applied_default")

    out, ids = [], set()
    for it in sorted(issues, key=lambda x: (SEVERITIES.index(x["severity"]), -x["keyword_volume"], x["check"],
                                            x["issue_id"])):
        if it["issue_id"] in ids:
            continue
        ids.add(it["issue_id"])
        if decided and it["issue_id"] in decided:
            it["status"] = f"decided:{decided[it['issue_id']]}"
        out.append(it)
    return out, groups


def backcheck(kw_rows, cl_rows, serp_urls=None, serp_t: int = 4, sim_t: float = 0.6, kw_fields=None,
              decided=None, also_in=None) -> list[dict]:
    """Issues (BACKCHECK_FIELDS dicts), most severe and biggest first. serp_urls maps a keyword, or (market,
    keyword), to its SERP URLs; decided maps an issue_id to the decision_id that settled it; also_in maps (market,
    decision_key(keyword)) to the other SEO groups the grouped file listed the keyword in."""
    return _check(kw_rows, cl_rows, serp_urls, serp_t, sim_t, kw_fields, decided, also_in)[0]


def proposals(issues: list[dict]) -> list[dict]:
    """One proposed decision per issue, in the decisions-file columns. Never applied by any script."""
    return [{"decision_id": "P-" + it["issue_id"], "action": it["proposed_action"], "market": it["market"],
             "keyword": it["proposed_keyword"], "target": it["proposed_target"], "value": it["proposed_value"],
             "reason": CHECK_TEXT[it["check"]], "evidence": it["evidence"], "source_issue": it["issue_id"],
             "author": "proposal", "date": ""} for it in issues if it["proposed_action"]]


def _write(path: str, fields: list[str], rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _md(v) -> str:
    return str(v).replace("|", "\\|").replace("\n", " ")


def write_backcheck(out_dir: str, kw_rows, cl_rows, serp_urls=None, serp_t: int = 4, sim_t: float = 0.6,
                    kw_fields=None, decided=None, also_in=None) -> str:
    """Write backcheck.csv, proposed-decisions.csv and backcheck-report.md; return a one-line summary."""
    issues, groups = _check(kw_rows, cl_rows, serp_urls, serp_t, sim_t, kw_fields, decided, also_in)
    props = proposals(issues)
    _write(os.path.join(out_dir, "backcheck.csv"), BACKCHECK_FIELDS, issues)
    _write(os.path.join(out_dir, "proposed-decisions.csv"), DECISION_FIELDS, props)
    n_seo = sum(g.prior for g in groups)
    mode = (f"prior: {n_seo:,} SEO groups and {len(groups) - n_seo:,} engine clusters" if n_seo else
            f"raw: {len(groups):,} engine clusters (no SEO grouping given)")
    sev = Counter(it["severity"] for it in issues)
    by_check: dict[str, Counter] = defaultdict(Counter)
    for it in issues:
        by_check[it["check"]][it["severity"]] += 1
    lines = ["# Back-check report", "",
             f"Groups checked: {len(groups):,} ({mode}). Issues: {len(issues):,}.", "",
             f"Thresholds: SERP overlap >= {serp_t} shared URLs (--serp-overlap); word overlap >= {sim_t} (--sim). "
             f"[Convention]: own-main word overlap below {LEX_FLOOR} is weak; mixed intent when the smaller side holds "
             f">= {MIXED_SHARE:.0%} of the group's volume; main not best when a member has >= {MAIN_RATIO}x its volume.",
             "",
             "Nothing here is applied. `proposed-decisions.csv` holds one proposed decision per issue (author "
             "'proposal'); to apply one, copy it into the decisions file with your own reason, evidence, author and "
             "date. Status `applied_default` = the script already did the default shown in the evidence.", "",
             "## Counts by check and severity", "",
             "| check | " + " | ".join(SEVERITIES) + " | total |", "|---|" + "---:|" * (len(SEVERITIES) + 1)]
    for check in sorted(by_check, key=lambda c: (-sum(by_check[c].values()), c)):
        c = by_check[check]
        lines.append(f"| {check} | " + " | ".join(str(c[s]) for s in SEVERITIES) + f" | {sum(c.values())} |")
    lines.append("| **total** | " + " | ".join(str(sev[s]) for s in SEVERITIES) + f" | {len(issues)} |")
    lines += ["", "## Issues by severity and volume", ""]
    if not issues:
        lines.append("No issue found.")
    else:
        lines += ["| issue | severity | check | market | group main | keyword | volume | evidence | proposed decision "
                  "| status |", "|---|---|---|---|---|---|---:|---|---|---|"]
        for it in issues[:REPORT_ROWS]:
            prop = " ".join(x for x in (it["proposed_action"], f"'{it['proposed_keyword']}'" if it["proposed_keyword"]
                                        else "", f"-> '{it['proposed_target']}'" if it["proposed_target"] else "",
                                        f"[{it['proposed_value']}]" if it["proposed_value"] else "") if x)
            lines.append("| " + " | ".join(_md(v) for v in (
                it["issue_id"], it["severity"], it["check"], it["market"], it["group_main"], it["keyword"],
                f"{it['keyword_volume']:,}", it["evidence"], prop, it["status"])) + " |")
        if len(issues) > REPORT_ROWS:
            lines += ["", f"{len(issues) - REPORT_ROWS:,} more issues in backcheck.csv."]
    with open(os.path.join(out_dir, "backcheck-report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return (f"Back-check: {len(issues):,} issues (" + ", ".join(f"{s}={sev[s]:,}" for s in SEVERITIES) +
            f") in {len(groups):,} groups, {len(props):,} proposed decisions (none applied): backcheck-report.md")
