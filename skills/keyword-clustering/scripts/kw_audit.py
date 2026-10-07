#!/usr/bin/env python3
"""Audit the SEO's grouping against the skill's rules and regroup where a rule fails (cluster_keywords.py --prior,
--prior-mode audit, the default). Standard library only.

The SEO's groups are the starting point, not a constraint: a group the rules have nothing against stays as it is
(the engine's lexical similarity never splits it: 'unique christmas gifts' and 'one of a kind christmas presents' may
be one post even if they share no word). A rule changes the grouping only on positive evidence:

  same_query       two groups whose main keywords are the same query (same words after normalisation: spelling,
                   word order, synonyms) or share >= --serp-overlap top-10 URLs: one post, merged into the group that
                   can win more traffic [Google: pages that compete for one query split their signals; Convention]
  duplicate        one keyword listed in several groups: kept where it is the main keyword, else in the group whose
                   main is closest to it; removed from the others (two pages would target it)
  shop_member      a pure shopping keyword ('buy ...', reader need 'shop') inside a blog group: split out (the shop
                   pages answer it; the topic map skips it)
  main_changed     the group's main keyword is not the best target: it has a year while an evergreen keyword exists,
                   or a member has >= 2x its volume, or a member wins >= 1.25x its winnable volume (KD against the
                   site's reach, kw_kd.py): the competitor's secondary keyword can be our main keyword
  export_topic     an export keyword in no SEO group that the engine clusters into a topic of its own (largest first)
  possible_duplicate  two groups the engine's lexical rule would merge (word overlap >= --sim, compatible cores, same
                   facets) but with no proof: NOT applied, check the live SERP (serp-check.csv / the SEO Audit sheet)
  noise_flag       an SEO keyword that matches a noise rule or filter: kept (the SEO chose it), listed to check

The topic map (topic_map.py) then audits the structure: the pillar of each group, groups too small to be posts of
their own (sections of the nearest post) and the hub of each pillar. Every change is one row of seo-audit.csv.
"""
from __future__ import annotations

import re
from collections import defaultdict

from kw_kd import KdModel

AUDIT_FIELDS = ["audit_id", "step", "market", "seo_group", "seo_main", "seo_kind", "seo_pillar", "check", "action",
                "keyword", "keyword_volume", "target_group", "target_main", "evidence_type", "evidence", "level"]
YEAR_RX = re.compile(r"\b(19|20)\d\d\b")
VOLUME_SWITCH = 2.0     # a member with 2x the main's volume names the post [Convention]
KD_SWITCH = 1.25        # ... or 1.25x its winnable volume, and at least KD_SWITCH_MIN more [Convention]
KD_SWITCH_MIN = 50
NATURAL_MARGIN = 0.3    # the new main must not read clearly less naturally (Fluency score per word pair)
MAX_EXPORT_TOPICS = 30
MAX_POSSIBLE = 40


def vkey(k) -> tuple:
    """The engine's variant key: market + canonical words in any order (dedupe() merges keywords with equal keys)."""
    return (k.market, tuple(sorted(k.tokens)))


def total(k) -> int:
    return k.volume + k.var_vol


ORDER_FILLER = frozenset({"to", "a", "an", "the", "for", "of", "in", "on", "at", "with", "and", "is", "are", "do",
                          "does", "your", "my", "you", "i"})


def same_order(a: tuple, b: tuple) -> bool:
    """The words two keywords share come in the same order: 'what to wear to work christmas party' and 'what to wear
    christmas party work' do not (an inverted tool phrasing never names a post)."""
    shared = (set(a) & set(b)) - ORDER_FILLER
    pa = [t for t in dict.fromkeys(a) if t in shared]
    pb = [t for t in dict.fromkeys(b) if t in shared]
    return pa == pb


def same_subject(seed, k) -> bool:
    """k asks the seed's question, maybe narrower: every subject word of the seed (its core) is in k's core, in the
    same word order."""
    return seed.core <= k.core and same_order(seed.tokens, k.tokens)


def jaccard(a, b) -> float:
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 0.0


WORD_RX = re.compile(r"[a-z0-9]+")


def choose_groups(rows: list) -> tuple[list[tuple], list[tuple]]:
    """A keyword the SEO listed in several groups (its rows were joined into one keyword with one tag per group): it
    stays in the group where it is the main keyword, else in the group whose main keyword shares most of its words;
    the chosen tag is put first (prior_clusters() uses it). Two groups that both name it as their main keyword ask
    the same query: they are returned to be merged. Returns ([(keyword, chosen tag, other tags, why)],
    [(group key kept, group key merged into it, keyword)])."""
    out, same_main = [], []
    for k in rows:
        tags = list(dict((t.group_key, t) for t in k.prior).values())
        if len(tags) < 2:
            continue
        mains = [t for t in tags if t.is_main]
        if len(mains) > 1:  # the main of several groups: those groups are merged into the first one (Audit.run)
            same_main += [(mains[0].group_key, t.group_key, k.keyword) for t in mains[1:]]
            tags = [t for t in tags if t.group_key not in {m.group_key for m in mains[1:]}]
            if len(tags) < 2:
                k.prior = (mains[0],) + tuple(t for t in k.prior if t is not mains[0])
                continue
            mains = mains[:1]
        mine = set(WORD_RX.findall(k.keyword.lower()))
        if mains:
            best, why = mains[0], f"it is the main keyword of group '{mains[0].group}'"
        else:
            def score(t):
                return jaccard(mine, WORD_RX.findall((t.main or "").lower()))
            best = max(tags, key=lambda t: (score(t), -tags.index(t)))
            why = f"its words are closest to that group's main '{best.main}' ({score(best):.2f})"
        k.prior = (best,) + tuple(t for t in k.prior if t is not best)
        out.append((k, best, [t for t in tags if t is not best], why))
    return out, same_main


class Audit:
    def __init__(self, kd: KdModel, fluency=None, serp_t: int = 4, sim_t: float = 0.6, weak=frozenset(),
                 plain=None, similar=None):
        self.kd, self.fluency, self.serp_t, self.sim_t, self.weak = kd, fluency, serp_t, sim_t, weak
        self.plain = plain or (lambda k: True)
        self.similar = similar  # (a seed, b seed) -> word overlap when the engine's lexical rule would merge, else 0
        self.rows: list[dict] = []

    # -- helpers
    def win(self, k) -> float:
        return self.kd.winnable(total(k), k.kd, k.kd_src)

    def group_win(self, cl) -> float:
        return sum(self.win(k) for k in cl)

    def tag(self, cl):
        return next((k.prior[0] for k in cl if k.prior), None)

    def log(self, cl, check, action, keyword="", volume="", target=None, etype="lexical", evidence="",
            level="[Convention]", step="cluster"):
        t = self.tag(cl) if cl else None
        tt = self.tag(target) if target else None
        self.rows.append({"audit_id": f"SA-{len(self.rows) + 1:04d}", "step": step, "market": cl[0].market if cl else "",
                          "seo_group": t.group if t else "", "seo_main": (t.main or cl[0].keyword) if t else "",
                          "seo_kind": t.group_role if t else "", "seo_pillar": t.pillar if t else "",
                          "check": check, "action": action, "keyword": keyword, "keyword_volume": volume,
                          "target_group": tt.group if tt else "", "target_main": target[0].keyword if target else "",
                          "evidence_type": etype, "evidence": evidence, "level": level})

    def fluent(self, k) -> float:
        return self.fluency.score(k.keyword) if self.fluency is not None else 0.0

    # -- rules
    def better_main(self, cl) -> tuple[object | None, str]:
        """(member, why) that should name the post instead of cl[0], or (None, ''). The SEO chose the main keyword,
        so another one names the post only when it asks the same thing (same subject words, same order, a phrasing
        that reads as naturally) and either has a year-free form, 2x the volume, or 1.25x the winnable volume while
        the SEO's main is above the site's reach."""
        seed = cl[0]
        pool = [k for k in cl if k is not seed and not k.fixed and self.plain(k) and len(k.keyword.split()) <= 8
                and same_subject(seed, k) and self.fluent(k) >= self.fluent(seed) - NATURAL_MARGIN]
        if YEAR_RX.search(seed.keyword):
            # the same query without the year: a variant folded into the main, or a member with all of its words
            forms = [(v, vol) for v, vol in zip(seed.variants, seed.var_vols)
                     if not YEAR_RX.search(v) and vol >= 0.2 * seed.volume]
            if forms:
                v, vol = max(forms, key=lambda x: (x[1], -len(x[0])))
                old, old_vol = seed.keyword, seed.volume
                i = seed.variants.index(v)
                seed.variants[i], seed.var_vols[i] = old, old_vol
                seed.keyword, seed.volume = v, vol
                return seed, (f"the main '{old}' names a year; '{v}' ({vol:,}/month, the same query) keeps one URL "
                              "that is refreshed every year")
            evergreen = [k for k in cl if k is not seed and not YEAR_RX.search(k.keyword) and not k.fixed
                         and k.tokset >= seed.tokset and same_subject(seed, k) and total(k) >= 0.2 * total(seed)]
            if evergreen:
                k = max(evergreen, key=lambda k: (self.win(k), total(k)))
                return k, (f"the main '{seed.keyword}' names a year; '{k.keyword}' ({total(k):,}/month) keeps one URL "
                           "that is refreshed every year")
        pool = [k for k in pool if not YEAR_RX.search(k.keyword)]
        best, why = None, ""
        hard = self.kd.label(seed.kd, seed.kd_src) != "easy"
        for k in sorted(pool, key=lambda k: (-self.win(k), -total(k), k.keyword)):
            if total(k) >= VOLUME_SWITCH * max(1, total(seed)) and self.fluent(k) >= self.fluent(seed):
                best, why = k, (f"'{k.keyword}' has {total(k):,} searches/month, {total(k) / max(1, total(seed)):.1f}x "
                                f"the main '{seed.keyword}' ({total(seed):,}; threshold {VOLUME_SWITCH:g}x)")
                break
            ws, wk = self.win(seed), self.win(k)
            if hard and self.kd.fit(k.kd, k.kd_src) > self.kd.fit(seed.kd, seed.kd_src) and \
                    wk >= KD_SWITCH * ws and wk - ws >= KD_SWITCH_MIN:
                best, why = k, (f"easier to rank: '{k.keyword}' KD {fmt(k.kd)} ({self.kd.label(k.kd, k.kd_src)}) wins "
                                f"~{wk:,.0f}/month against ~{ws:,.0f} for '{seed.keyword}' (KD {fmt(seed.kd)}, "
                                f"{self.kd.label(seed.kd, seed.kd_src)}); {self.kd.describe()}")
                break
        return best, why

    def run(self, seo: list[list], free: list[list], same_main: list[tuple] | None = None) -> list[list]:
        groups = [list(c) for c in seo]
        alive = [True] * len(groups)

        def merge(i: int, j: int, etype: str, evidence: str) -> None:
            """Merge group j into group i (i survives)."""
            self.log(groups[j], "same_query", "merged", groups[j][0].keyword, total(groups[j][0]), groups[i], etype,
                     evidence, "[Google: one page per query; Convention]")
            groups[i].extend(groups[j])
            groups[j] = []
            alive[j] = False

        # 1. same_query: two groups that name the same keyword as their main, equal main keys, SERP overlap of the mains
        index: dict[tuple, int] = {}
        for i, cl in enumerate(groups):
            for k in cl:
                if k.prior:
                    index.setdefault((k.prior[0].group_key, k.market), i)
        for keep_key, drop_key, kw in same_main or []:
            for market in {k.market for cl in groups for k in cl}:
                i, j = index.get((keep_key, market)), index.get((drop_key, market))
                if i is not None and j is not None and i != j and alive[i] and alive[j]:
                    merge(i, j, "lexical", f"both groups name '{kw}' as their main keyword: one query, one post")
        by_main: dict[tuple, list[int]] = defaultdict(list)
        for i, cl in enumerate(groups):
            if alive[i] and cl:
                by_main[vkey(cl[0])].append(i)
        for key, idx in by_main.items():
            if len(idx) < 2:
                continue
            idx = sorted(idx, key=lambda i: (-self.group_win(groups[i]), i))
            for j in idx[1:]:
                merge(idx[0], j, "lexical", f"the main keywords '{groups[j][0].keyword}' and '{groups[idx[0]][0].keyword}' "
                      f"have the same words after normalisation ('{' '.join(key[1])}')")
        if self.serp_t:
            mains = [(i, cl[0]) for i, cl in enumerate(groups) if alive[i] and cl[0].urls]
            for a in range(len(mains)):
                for b in range(a + 1, len(mains)):
                    (i, ki), (j, kj) = mains[a], mains[b]
                    if not (alive[i] and alive[j]) or ki.market != kj.market:
                        continue
                    shared = len(ki.urls & kj.urls)
                    if shared >= self.serp_t:
                        keep, drop = (i, j) if self.group_win(groups[i]) >= self.group_win(groups[j]) else (j, i)
                        merge(keep, drop, "serp", f"the main keywords share {shared} top-10 URLs (threshold "
                              f"{self.serp_t}): Google answers both with the same pages")
        # 2. duplicate: one keyword in several groups
        where: dict[tuple, list[tuple[int, object]]] = defaultdict(list)
        for i, cl in enumerate(groups):
            for k in cl:
                where[vkey(k)].append((i, k))
        for key, hits in where.items():
            gs = {i for i, _ in hits}
            if len(gs) < 2:
                continue
            mains = [i for i, k in hits if k is groups[i][0]]
            if mains:
                win = mains[0]
                why = f"it is the main keyword of group '{self.tag(groups[win]).group if self.tag(groups[win]) else ''}'"
            else:
                win = max(gs, key=lambda i: (jaccard(hits[0][1].tokens, groups[i][0].tokens), self.group_win(groups[i]), -i))
                why = (f"its words are closest to that group's main '{groups[win][0].keyword}' "
                       f"({jaccard(hits[0][1].tokens, groups[win][0].tokens):.2f})")
            keep = next(k for i, k in hits if i == win)
            for i, k in hits:
                if i == win or k is groups[i][0] or k is keep:
                    continue
                groups[i].remove(k)  # folded into the kept keyword as a variant, as dedupe() does within a group
                keep.variants = keep.variants + [k.keyword] + k.variants
                keep.var_vols = keep.var_vols + [k.volume] + k.var_vols
                keep.var_vol += k.volume + k.var_vol
                keep.urls = keep.urls | k.urls
                self.log(groups[i] or [k], "duplicate", "removed", k.keyword, total(k), groups[win], "lexical",
                         f"'{k.keyword}' is listed in {len(gs)} groups (the same words as '{keep.keyword}'); kept in "
                         f"'{groups[win][0].keyword}' because {why}, as a variant: two posts would compete for it",
                         "[Convention]")
        # 3. shopping keywords out of blog groups
        out: list[list] = []
        for i, cl in enumerate(groups):
            if not alive[i] or not cl:
                continue
            if cl[0].fit != "low":
                for k in [k for k in cl[1:] if k.fit == "low"]:
                    cl.remove(k)
                    out.append([k])
                    self.log(cl, "shop_member", "split", k.keyword, total(k), None, "lexical",
                             f"'{k.keyword}' asks to buy (reader need '{k.need}'): the shop pages answer it, not a blog "
                             "post; split out of the group (the topic map skips it)", "[Convention]")
            # 4. the main keyword
            new, why = self.better_main(cl)
            if new is not None:
                if new is not cl[0]:
                    cl.remove(new)
                    cl.insert(0, new)
                self.log(cl, "main_changed", "main_changed", new.keyword, total(new), None,
                         "kd" if why.startswith("easier") else "volume", why, "[Convention]")
            out.append(cl)
        for cl in out:
            if cl[0].prior:
                for k in cl:
                    if k.prior and k.prior[0].group_key != cl[0].prior[0].group_key:
                        k.joined = "audit:merged"
        # 5. possible duplicates the words suggest but nothing proves (not applied): one row per smaller group, with
        # the group it is closest to; only groups that share a word are compared
        if self.similar is not None:
            seeds = [cl for cl in out if cl[0].prior and cl[0].fit != "low"]
            gw = [self.group_win(cl) for cl in seeds]  # once per group: the pair loop below is the hot spot
            by_tok: dict[tuple, list[int]] = defaultdict(list)
            for i, cl in enumerate(seeds):
                for t in cl[0].tokset:
                    by_tok[(cl[0].market, t)].append(i)
            best: dict[int, tuple] = {}
            for i, cl in enumerate(seeds):
                cand = {j for t in cl[0].tokset for j in by_tok[(cl[0].market, t)][:500] if j != i}
                for j in cand:
                    small, big = (i, j) if (gw[i], -i) < (gw[j], -j) else (j, i)
                    if small != i:
                        continue
                    sim = self.similar(seeds[i][0], seeds[j][0])
                    if sim and (small not in best or (sim, gw[big]) > best[small][:2]):
                        best[small] = (sim, gw[big], big)
            for small, (sim, _, big) in sorted(best.items(), key=lambda kv: -kv[1][0])[:MAX_POSSIBLE]:
                cl, other = seeds[small], seeds[big]
                self.log(cl, "possible_duplicate", "check_serp", cl[0].keyword, total(cl[0]), other, "lexical",
                         f"word overlap {sim:.2f} with '{other[0].keyword}' and the same subject words; not merged "
                         "without proof: if the live SERPs share >= 4 of their top-10 URLs, merge them (decision "
                         "'merge'); a group too small for a post of its own becomes a section anyway (topic map)",
                         "[Convention]")
        # 6. export topics the SEO's file does not have
        topics = sorted((cl for cl in free if cl[0].fit != "low"), key=lambda c: -self.group_win(c))
        for cl in topics[:MAX_EXPORT_TOPICS]:
            self.log(cl, "export_topic", "added", cl[0].keyword, sum(total(k) for k in cl), None, "lexical",
                     f"{len(cl)} export keyword(s) in no SEO group ({sum(total(k) for k in cl):,}/month, KD "
                     f"{fmt(cl[0].kd)}): planned like any cluster", "[Convention]")
        return out + free

    def duplicates(self, chosen: list[tuple]) -> None:
        for k, best, others, why in chosen:
            for t in others:
                self.rows.append({"audit_id": f"SA-{len(self.rows) + 1:04d}", "step": "cluster", "market": k.market,
                                  "seo_group": t.group, "seo_main": t.main, "seo_kind": t.group_role,
                                  "seo_pillar": t.pillar, "check": "duplicate", "action": "removed",
                                  "keyword": k.keyword, "keyword_volume": total(k), "target_group": best.group,
                                  "target_main": best.main, "evidence_type": "lexical",
                                  "evidence": f"'{k.keyword}' is listed in {len(others) + 1} groups; kept in group "
                                              f"'{best.group}' because {why}: two posts would compete for it",
                                  "level": "[Convention]"})

    def noise(self, hits) -> None:
        for kw, market, volume, why, group in hits:
            self.rows.append({"audit_id": f"SA-{len(self.rows) + 1:04d}", "step": "cluster", "market": market,
                              "seo_group": group, "seo_main": "", "seo_kind": "", "seo_pillar": "",
                              "check": "noise_flag", "action": "kept", "keyword": kw, "keyword_volume": volume,
                              "target_group": "", "target_main": "", "evidence_type": "rule",
                              "evidence": f"matches '{why}'; kept because the SEO chose it: drop it with a decision "
                                          "'drop_keyword' if the rule is right", "level": "[Convention]"})


def fmt(v) -> str:
    return "-" if v is None else f"{v:g}"
