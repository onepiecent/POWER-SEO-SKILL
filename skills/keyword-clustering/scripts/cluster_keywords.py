#!/usr/bin/env python3
"""Cluster keywords from an SEO specialist's export file, on request. Standard library only.

Input   : one or more CSV or Excel (.xlsx) files (Semrush / Ahrefs / Google Keyword Planner / GSC / Google Sheets).
          Syntax  file.csv::uk  assigns a market to a file that has no country column.
Output  : <out>/cluster-report.md     report on file reading, filters, results and warnings (READ FIRST)
          <out>/clusters.csv          one row per cluster = one blog post (input of topic-map)
          <out>/keyword-map.csv       one row per keyword
          <out>/groups.csv, groups.md groups by --group-by
          <out>/excluded.csv          excluded keywords + reason (nothing is dropped silently)
          <out>/unclassified.csv, taxonomy-suggestions.csv   unrecognised keywords + taxonomy extension hints
          <out>/merge-candidates.csv  pairs of nearby clusters for a person/Claude to review

Two levels: CLUSTER (keywords with the same search intent -> one post), then GROUP (--group-by: groups the clusters
along the dimension you ask for: occasion, recipient, interest, product, style, craft, category, intent...).

How clusters are formed:
  * Typos and split words are fixed first, learned from the file itself (thanksgivng, thanks giving -> thanksgiving).
  * Both keywords have serp_urls -> same cluster when >= --serp-overlap URLs overlap.
  * Otherwise                    -> weighted Jaccard on tokens >= --sim.
  * Facet guard: occasion, recipient (including implied), interest, product and theme must match before a lexical merge.
  * Then clusters that ask the same thing in other words are merged into one post: same guard and the same core
    ('when is thanksgiving' = 'what day is thanksgiving 2026' = 'thanksgiving 2026 date'). --no-consolidate turns it off.
  * Each market (us/uk) is clustered separately because the SERPs differ.
  * Large files are sped up with an inverted index + prefix filter, so pairs are not compared one by one.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kw_ingest import ALIASES, norm_market, parse_number, read_keywords  # noqa: E402
from kw_text import (FACET_ORDER, IMPLIED_RECIPIENT, Categories, Fluency, NoiseRules, Respeller,  # noqa: E402
                     Taxonomy, normalize_text, weighted_jaccard)

GRANULARITY = {"tight": (0.75, 5), "normal": (0.6, 4), "loose": (0.45, 3)}
LIST_NEEDS = {"inspire", "choose"}  # these two usually share one listicle post
GROUP_FIELDS = {"occasion": "occasion", "recipient": "recipient", "interest": "interest", "product": "product",
                "style": "style", "craft": "craft", "theme": "theme", "category": "category", "season": "season",
                "market": "market", "intent": "reader_need", "need": "reader_need", "reader_need": "reader_need",
                "blog_fit": "blog_fit"}
MERGE_LEX_FLOOR = 0.34
YEAR_KW_RX = re.compile(r"\b(19|20)\d\d\b")
MAX_POSTING = 3000


class KW:
    __slots__ = ("keyword", "tokens", "tokset", "volume", "vol_est", "kd", "cpc", "market", "urls", "occasion",
                 "recipient", "interest", "product", "style", "craft", "theme", "core", "need", "fit", "terms",
                 "category", "variants", "var_vols", "var_vol", "parent", "intent_src", "src", "ngroup", "fixed")

    def facets(self) -> dict:
        return {f: getattr(self, f) for f in FACET_ORDER}


def eff_recipient(k: KW) -> str:
    return k.recipient or IMPLIED_RECIPIENT.get(k.occasion, "")


def cores_compatible(a: frozenset, b: frozenset) -> bool:
    """Shared words are not enough when the two keywords ask different things: 'day of thanksgiving' (core empty: the
    date) must not join 'day after thanksgiving' (core {after}). Cores must be equal, or overlap by half."""
    if a == b:
        return True
    return bool(a and b) and len(a & b) / len(a | b) >= 0.5


def part_key(k: KW) -> tuple:
    """Two keywords may only be merged lexically when they share the market, the intent group and the SAME occasion,
    recipient (including implied: mother's day -> mom), interest, product and theme. 'gifts for mom' and
    'mother's day gifts for mom' are two different posts; 'gifts for dog lovers' differs from 'gifts for dog moms';
    'thanksgiving trivia' (facts) differs from 'thanksgiving games' (activities)."""
    return (k.market, k.ngroup, k.occasion, eff_recipient(k), k.interest, k.product, k.theme)


# --------------------------------------------------------------------------- ingest + filters
def parse_map(items) -> dict:
    out = {}
    for it in items or []:
        if "=" not in it:
            raise SystemExit(f"--map needs the form canonical_column=Column name in the file, got: {it}")
        k, v = it.split("=", 1)
        if k.strip() not in ALIASES:
            raise SystemExit(f"--map: invalid canonical column '{k}'. Valid: {', '.join(ALIASES)}")
        out[k.strip()] = v.strip()
    return out


def parse_only(items) -> dict:
    out = {}
    for it in items or []:
        if "=" not in it:
            raise SystemExit(f"--only needs the form facet=value1,value2, got: {it}")
        k, v = it.split("=", 1)
        k = {**GROUP_FIELDS, 'season': 'occasion'}.get(k.strip(), k.strip())
        out.setdefault(k, set()).update(x.strip() for x in v.split(",") if x.strip())
    return out


def ingest(args, tax: Taxonomy, noise, cats):
    include_rx = [re.compile(p, re.I) for p in args.include or []]
    exclude_rx = [(p, re.compile(p, re.I)) for p in args.exclude or []]
    only = parse_only(args.only)
    overrides = parse_map(args.map)
    default_market = norm_market(args.market) if args.market else ""
    kept: list[KW] = []
    excluded: list[tuple] = []
    reasons: Counter = Counter()
    infos, warnings = [], []
    total_rows = 0
    loaded = []
    for spec in args.files:
        path, sep, mk = spec.rpartition("::")
        if not sep:
            path, mk = spec, ""
        table = read_keywords(path, overrides)
        loaded.append((os.path.basename(path), table.info, norm_market(mk) if mk else default_market, list(table)))
        infos.append(table.info)
    # Typos and split words are learned from every row of every file BEFORE any filter, so 'thanksgivng day' is kept by
    # --only occasion=thanksgiving and merged with 'thanksgiving day'.
    respeller = Respeller()
    if not args.no_respell:  # learn from English rows only: Spanish words must not become correction targets
        docs = []
        for _, _, _, recs in loaded:
            for rec in recs:
                raw = rec.get("keyword", "")
                norm0 = normalize_text(raw)
                if noise is None or noise.check(raw.lower(), norm0, language_only=True) is None:
                    docs.append(norm0.split())
        respeller = Respeller.learn(docs)
    respelled = 0
    for src, info, file_market, records in loaded:
        vsrc = info["volume_source"]
        if vsrc == "none":
            warnings.append(f"{src}: no volume/impressions column; every volume is 0, so the priority order is meaningless.")
        elif vsrc != "volume":
            warnings.append(f"{src}: using column '{info['columns'][vsrc]}' as volume; this is NOT search volume. "
                            "Impressions only reflect queries the site was already shown for, not total market demand; "
                            "add volume from Semrush/Ahrefs/Keyword Planner.")
        for rec in records:
            total_rows += 1
            raw_kw = re.sub(r"\s+", " ", rec.get("keyword", "")).strip()
            norm0 = normalize_text(raw_kw)
            if not norm0:
                reasons["empty_keyword"] += 1
                continue
            norm = respeller.apply(norm0)
            respelled += norm != norm0
            low = raw_kw.lower()
            vol_raw = rec.get(vsrc) if vsrc != "none" else None
            vol, est = parse_number(vol_raw, integer=True, range_mode=args.range_mode)
            volume = int(vol) if vol is not None else 0
            reason = None
            if noise is not None:  # language is judged on the original words ('celebracion' is a Spanish marker)
                reason = noise.check(low, norm0)
                if reason is None and norm != norm0:
                    reason = noise.check(low, norm, skip_language=True)
            if reason is None and vsrc != "none":
                if args.min_volume and volume < args.min_volume:
                    reason = "filter:min_volume"
                elif args.max_volume and volume > args.max_volume:
                    reason = "filter:max_volume"
            kd, _ = parse_number(rec.get("kd"))
            if reason is None and args.max_kd is not None and kd is not None and kd > args.max_kd:
                reason = "filter:max_kd"
            if reason is None and include_rx and not any(rx.search(norm) or rx.search(low) for rx in include_rx):
                reason = "filter:include_no_match"
            if reason is None:
                for pat, rx in exclude_rx:
                    if rx.search(norm) or rx.search(low):
                        reason = f"filter:exclude:{pat}"
                        break
            if reason:
                reasons[reason] += 1
                excluded.append((raw_kw, volume, reason, src))
                continue
            facets = tax.detect_facets(norm)
            need = tax.classify_need(norm, facets)
            category, _ = cats.assign(norm) if cats else ("", [])
            k = KW()
            k.keyword, k.volume, k.vol_est, k.kd = raw_kw, volume, est, kd
            k.fixed = norm != norm0
            k.cpc = parse_number(rec.get("cpc"))[0]
            mk_row = norm_market(rec.get("market")) if rec.get("market") else ""
            k.market = mk_row or file_market or "all"
            k.tokens = tuple(tax.canon_tokens(norm))
            k.tokset = frozenset(k.tokens)
            k.core = tax.core_tokens(norm, facets["theme"])
            k.urls = frozenset(_norm_url(u) for u in re.split(r"[|\s]+", rec.get("serp", "")) if u.strip())
            for f in FACET_ORDER:
                setattr(k, f, facets[f])
            k.need, k.fit = need, tax.blog_fit[need]
            k.ngroup = "list" if need in LIST_NEEDS else need
            k.terms = tax.market_terms(norm)
            k.category, k.variants, k.var_vols, k.var_vol = category, [], [], 0
            k.parent = normalize_text(rec.get("parent", "")) if rec.get("parent") else ""
            k.intent_src, k.src = rec.get("intent", ""), src
            if only and not _passes_only(k, only):
                reasons["filter:only"] += 1
                excluded.append((raw_kw, volume, "filter:only", src))
                continue
            if args.drop_shop and need == "shop":
                reasons["filter:drop_shop"] += 1
                excluded.append((raw_kw, volume, "filter:drop_shop", src))
                continue
            kept.append(k)
        if info["rows"] == 0:
            warnings.append(f"{src}: no data rows could be read.")
    respell = {"typos": respeller.typos, "joins": respeller.joins, "splits": respeller.splits,
               "completions": respeller.completions, "keywords_changed": respelled}
    return kept, excluded, reasons, infos, warnings, total_rows, respell


def _norm_url(u: str) -> str:
    u = re.sub(r"^https?://(www\.)?", "", u.strip().lower())
    return re.split(r"[?#]", u)[0].rstrip("/")


def _passes_only(k: KW, only: dict) -> bool:
    for field, values in only.items():
        attr = {"reader_need": "need", "blog_fit": "fit"}.get(field, field)
        if not hasattr(k, attr) or getattr(k, attr) not in values:
            return False
    return True


def prefer(a: KW, b: KW) -> bool:
    """True when a should name the merged keyword instead of b: the version without a year when it has at least 20%
    of the dated one's volume ('when is thanksgiving' rather than 'when is thanksgiving 2026'), else the bigger one."""
    ya, yb = bool(YEAR_KW_RX.search(a.keyword)), bool(YEAR_KW_RX.search(b.keyword))
    if ya != yb:
        plain, dated = (b, a) if ya else (a, b)
        return (plain if plain.volume >= 0.2 * dated.volume else dated) is a
    return a.volume > b.volume


def dedupe(rows: list[KW]) -> tuple[list[KW], int]:
    """Merge same-meaning variants (mom/mum, word order, added year, fixed typo) within a market; the kept keyword
    lists the others (and their volumes) as variants."""
    best: dict[tuple, KW] = {}
    merged = 0
    for r in rows:
        key = (r.market, tuple(sorted(r.tokens)))
        cur = best.get(key)
        if cur is None:
            best[key] = r
            continue
        merged += 1
        keep, drop = (r, cur) if prefer(r, cur) else (cur, r)
        keep.variants = cur.variants + r.variants + [drop.keyword]
        keep.var_vols = cur.var_vols + r.var_vols + [drop.volume]
        keep.var_vol = cur.var_vol + r.var_vol + drop.volume
        keep.urls = keep.urls | drop.urls
        best[key] = keep
    return list(best.values()), merged


# --------------------------------------------------------------------------- clustering
class Clusterer:
    def __init__(self, rows: list[KW], weak: frozenset, sim_t: float, serp_t: int, trust_parent: bool):
        self.weak, self.sim_t, self.serp_t, self.trust_parent = weak, sim_t, serp_t, trust_parent
        self.df: Counter = Counter()
        for r in rows:
            self.df.update(r.tokset)
        self.rows = sorted(rows, key=lambda r: (-r.volume, r.keyword))
        self.clusters: list[list[KW]] = []
        self.part_index: dict[tuple, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
        self.url_index: dict[str, list[int]] = defaultdict(list)
        self.parent_index: dict[tuple, int] = {}

    def prefix_tokens(self, k: KW, thr: float) -> list[str]:
        """Prefix filter: two sets with Jaccard >= thr must share at least one token outside the tail (the most common
        tokens whose total weight is < thr * W). So only clusters that share a rare token need to be checked."""
        toks = sorted(k.tokset, key=lambda t: (self.df.get(t, 0), t))
        weights = [0.3 if t in self.weak else 1.0 for t in toks]
        need, acc, cut = thr * sum(weights), 0.0, len(toks)
        for w in reversed(weights):
            if acc + w < need - 1e-9:
                acc += w
                cut -= 1
            else:
                break
        return toks[:cut]

    def _lex_candidates(self, k: KW, thr: float) -> set[int]:
        prefix, cand = self.prefix_tokens(k, thr), set()
        index = self.part_index.get(part_key(k))
        if index:
            for tok in prefix:
                lst = index.get(tok)
                if lst:
                    cand.update(lst[:MAX_POSTING])
        return cand

    def _serp_counts(self, k: KW) -> Counter:
        counts: Counter = Counter()
        for u in k.urls:
            for i in self.url_index.get(u, ())[:MAX_POSTING]:
                counts[i] += 1
        return counts

    def find(self, k: KW) -> int | None:
        best, best_score = None, None
        if self.trust_parent and k.parent:
            i = self.parent_index.get((k.market, k.parent, k.ngroup))
            if i is not None:
                return i
        if k.urls:
            for i, c in self._serp_counts(k).items():
                if c >= self.serp_t:
                    seed = self.clusters[i][0]
                    if seed.market == k.market:  # matching SERPs are stronger evidence than the facet guard
                        score = (2, c, -i)
                        if best_score is None or score > best_score:
                            best, best_score = i, score
        for i in self._lex_candidates(k, self.sim_t):
            seed = self.clusters[i][0]
            if seed.urls and k.urls:
                continue  # when both have SERP data, trust only the SERP
            s = weighted_jaccard(k.tokset, seed.tokset, self.weak)
            if s >= self.sim_t and cores_compatible(k.core, seed.core):
                score = (1, s, -i)
                if best_score is None or score > best_score:
                    best, best_score = i, score
        return best

    def _register(self, i: int) -> None:
        seed = self.clusters[i][0]
        index = self.part_index[part_key(seed)]
        for tok in seed.tokset:
            index[tok].append(i)
        for u in seed.urls:
            self.url_index[u].append(i)
        if seed.parent:
            self.parent_index.setdefault((seed.market, seed.parent, seed.ngroup), i)

    def run(self) -> list[list[KW]]:
        for r in self.rows:
            i = self.find(r)
            if i is None:
                self.clusters.append([r])
                self._register(len(self.clusters) - 1)
            else:
                self.clusters[i].append(r)
        return self.clusters

    def merge_candidates(self, limit: int = 300) -> list[tuple]:
        out = []
        for i, cl in enumerate(self.clusters):
            k = cl[0]
            for j in self._lex_candidates(k, MERGE_LEX_FLOOR):
                if j >= i:
                    continue
                seed = self.clusters[j][0]
                if seed.urls and k.urls:
                    continue
                s = weighted_jaccard(k.tokset, seed.tokset, self.weak)
                if MERGE_LEX_FLOOR <= s < self.sim_t:
                    out.append((s, j, i, f"tokens close together {s:.2f} (merge threshold {self.sim_t})"))
            if k.urls:
                for j, c in self._serp_counts(k).items():
                    seed = self.clusters[j][0]
                    if j < i and 2 <= c < self.serp_t and seed.market == k.market:
                        out.append((c / self.serp_t, j, i, f"SERP overlap {c} URLs (threshold {self.serp_t})"))
            if k.parent:
                j = self.parent_index.get((k.market, k.parent, k.ngroup))
                if j is not None and j < i and not self.trust_parent:
                    out.append((0.5, j, i, f"same Parent Topic: {k.parent}"))
        out.sort(key=lambda x: -x[0])
        return out[:limit]


def consolidate(clusters: list[list[KW]]) -> tuple[list[list[KW]], list[int]]:
    """Merge clusters that ask the same thing in other words into one post: same guard (part_key) and the same core of
    the seed keyword. 'when is thanksgiving', 'what day is thanksgiving 2026' and 'thanksgiving 2026 date' share
    theme=dates and an empty core, so they become one post; 'is thanksgiving always on a thursday' (core {thursday})
    stays a post of its own. Clusters built from SERP overlap are left as they are (the SERP is stronger evidence).
    Returns the new clusters and, for every old cluster index, the index of the cluster it ended up in."""
    groups: dict[tuple, int] = {}
    out: list[list[KW]] = []
    owner: list[int] = []
    for i, cl in enumerate(clusters):  # clusters were created in volume order: the first one of a key keeps its seed
        seed = cl[0]
        # within one theme and one core, a list query and a question are the same topic ('thanksgiving traditions' =
        # 'what are some thanksgiving traditions'); how-to, copy ideas and shopping stay apart
        group = "list" if seed.ngroup in ("list", "info") else seed.ngroup
        key = ("serp", i) if seed.urls else (seed.market, group, *part_key(seed)[2:], seed.core)
        j = groups.get(key)
        if j is None:
            groups[key] = j = len(out)
            out.append(list(cl))
        else:
            out[j].extend(cl)
        owner.append(j)
    for cl in out:
        cl[1:] = sorted(cl[1:], key=lambda r: (-(r.volume + r.var_vol), r.keyword))
    return out, owner



QUESTION_LAST_RX = re.compile(r"\b(why|how|what|when|where|who|which)\s*$")
NATURAL_BAND = 0.8     # a more natural phrasing may name the post when it has >= 80% of the chosen keyword's volume
NATURAL_MARGIN = 0.3   # ... and is clearly more natural (Fluency score, mean log probability per word pair)


def evergreen_seed(cl: list[KW], fluency: Fluency | None = None) -> list[KW]:
    """Choose the cluster's name (main keyword and slug) among its strong keywords:
    * without a year when one has at least 20% of the top volume: a seasonal post keeps one URL and is refreshed
      every year, so 'when is thanksgiving' beats 'thanksgiving 2025';
    * never a keyword typed with a typo when a correctly spelled one exists;
    * then, among keywords with at least half of the best volume, prefer a natural phrase over an inverted one
      ('why do we eat turkey on thanksgiving' over 'turkey thanksgiving why');
    * finally, a phrasing with >= 80% of that volume that reads clearly more naturally wins: 'true story of
      thanksgiving' (1,300) over 'real story thanksgiving' (1,600), 'thanksgiving facts for kids' over
      '... for kindergarteners'. Semrush rounds volumes into steps, so such pairs are often tied or one step apart."""
    top = cl[0]
    pool = [r for r in cl if not YEAR_KW_RX.search(r.keyword)]
    if not pool or max(r.volume for r in pool) < 0.2 * top.volume:
        pool = cl
    pool = [r for r in pool if not r.fixed] or pool
    best_vol = max(r.volume for r in pool)
    strong = [r for r in pool if r.volume >= 0.5 * best_vol]

    def plain(r: KW) -> bool:
        return not QUESTION_LAST_RX.search(r.keyword.lower()) and not any(ch.isdigit() for ch in r.keyword)
    seed = max(strong, key=lambda r: (plain(r), r.volume, -len(r.keyword)))
    if fluency is not None and plain(seed):
        band = [r for r in strong if r is seed or (plain(r) and r.volume >= NATURAL_BAND * seed.volume
                                                    and len(r.keyword.split()) <= 8)]
        natural = max(band, key=lambda r: (fluency.score(r.keyword), r.volume, -len(r.keyword)))
        if fluency.score(natural.keyword) >= fluency.score(seed.keyword) + NATURAL_MARGIN:
            seed = natural
    if seed is not top:
        cl.remove(seed)
        cl.insert(0, seed)
    return cl


# --------------------------------------------------------------------------- outputs
KW_FIELDS = ["cluster_id", "market", "keyword", "volume", "volume_estimated", "kd", "cpc", "is_seed", "reader_need",
             "blog_fit", "occasion", "recipient", "interest", "product", "style", "craft", "theme", "category",
             "market_terms", "parent_topic", "intent_source", "variants", "source_file", "spelling_fixed",
             "variant_volumes"]
CL_FIELDS = ["cluster_id", "market", "cluster_name", "keyword_count", "seed_volume", "cluster_volume", "seed_kd",
             "kd_min", "reader_need", "blog_fit", "occasion", "recipient", "interest", "product", "style", "craft",
             "theme", "core", "category", "season", "market_terms", "parent_topic", "keywords", "name_fluency"]


def build_rows(clusters: list[list[KW]], tax: Taxonomy, fluency: Fluency | None = None):
    kw_rows, cl_rows, ids = [], [], {}
    ordered = sorted(clusters, key=lambda c: (-sum(r.volume + r.var_vol for r in c), c[0].keyword))
    for n, cl in enumerate(ordered, 1):
        seed = cl[0]
        cid = f"C{n:04d}"
        ids[id(cl)] = cid
        kds = [r.kd for r in cl if r.kd is not None]
        terms = {r.terms for r in cl} - {"none"}
        for r in cl:
            kw_rows.append({"cluster_id": cid, "market": r.market, "keyword": r.keyword, "volume": r.volume,
                            "volume_estimated": int(r.vol_est), "kd": "" if r.kd is None else int(r.kd),
                            "cpc": "" if r.cpc is None else r.cpc, "is_seed": int(r is seed), "reader_need": r.need,
                            "blog_fit": r.fit, "occasion": r.occasion, "recipient": r.recipient,
                            "interest": r.interest, "product": r.product, "style": r.style, "craft": r.craft,
                            "theme": r.theme, "category": r.category, "market_terms": r.terms, "parent_topic": r.parent,
                            "intent_source": r.intent_src, "variants": "|".join(r.variants), "source_file": r.src,
                            "spelling_fixed": int(r.fixed), "variant_volumes": "|".join(str(v) for v in r.var_vols)})
        cl_rows.append({"cluster_id": cid, "market": seed.market, "cluster_name": seed.keyword,
                        "keyword_count": len(cl) + sum(len(r.variants) for r in cl), "seed_volume": seed.volume,
                        "cluster_volume": sum(r.volume + r.var_vol for r in cl), "seed_kd": "" if seed.kd is None else int(seed.kd),
                        "kd_min": "" if not kds else int(min(kds)), "reader_need": seed.need, "blog_fit": seed.fit,
                        "occasion": seed.occasion, "recipient": seed.recipient, "interest": seed.interest,
                        "product": seed.product, "style": seed.style, "craft": seed.craft, "theme": seed.theme,
                        "core": " ".join(sorted(seed.core)), "category": seed.category,
                        "season": seed.occasion if seed.occasion in tax.seasonal else "",
                        "market_terms": "mixed" if len(terms) > 1 else (next(iter(terms)) if terms else "none"),
                        "parent_topic": seed.parent, "keywords": "|".join(r.keyword for r in cl[:15]),
                        "name_fluency": f"{fluency.score(seed.keyword):.2f}" if fluency else ""})
    return kw_rows, cl_rows, ids, ordered


def write_csv(path: str, fields: list[str], rows) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields) if rows and isinstance(rows[0], dict) else csv.writer(fh)
        if isinstance(w, csv.DictWriter):
            w.writeheader()
            w.writerows(rows)
        else:
            w.writerow(fields)
            w.writerows(rows)


def build_groups(cl_rows: list[dict], dims: list[str]):
    fields = [GROUP_FIELDS[d] for d in dims]
    groups: dict[tuple, dict] = {}
    for r in cl_rows:
        key = tuple(r[f] or "(none)" for f in fields)
        g = groups.setdefault(key, {"clusters": [], "keywords": 0, "volume": 0})
        g["clusters"].append(r)
        g["keywords"] += r["keyword_count"]
        g["volume"] += r["cluster_volume"]
    total = sum(g["volume"] for g in groups.values()) or 1
    out = []
    for key, g in sorted(groups.items(), key=lambda kv: -kv[1]["volume"]):
        top = sorted(g["clusters"], key=lambda r: -r["cluster_volume"])
        out.append({"group": " / ".join(key), **{d: v for d, v in zip(dims, key)}, "clusters": len(g["clusters"]),
                    "keywords": g["keywords"], "volume": g["volume"], "volume_share_pct": round(100 * g["volume"] / total, 1),
                    "top_clusters": " | ".join(r["cluster_name"] for r in top[:5]), "_rows": top})
    return out


def write_groups(out_dir: str, groups: list[dict], dims: list[str], top_n: int) -> None:
    fields = ["group", *dims, "clusters", "keywords", "volume", "volume_share_pct", "top_clusters"]
    write_csv(os.path.join(out_dir, "groups.csv"), fields, [{k: g[k] for k in fields} for g in groups])
    lines = [f"# Groups by: {', '.join(dims)}", "", f"{len(groups)} groups. Showing the {min(top_n, len(groups))} largest.", ""]
    for g in groups[:top_n]:
        lines += [f"## {g['group']}  ·  {g['clusters']} clusters · {g['keywords']} keywords · volume {g['volume']:,} "
                  f"({g['volume_share_pct']}%)", "", "| Cluster | Keywords | Volume | Reader need | Blog fit |", "|---|---:|---:|---|---|"]
        for r in g["_rows"][:15]:
            lines.append(f"| {r['cluster_name']} | {r['keyword_count']} | {r['cluster_volume']:,} | {r['reader_need']} | {r['blog_fit']} |")
        if len(g["_rows"]) > 15:
            lines.append(f"| … and {len(g['_rows']) - 15} more clusters (see clusters.csv) | | | | |")
        lines.append("")
    with open(os.path.join(out_dir, "groups.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def suggest_terms(unclassified: list[KW], tax: Taxonomy, top: int = 200) -> list[list]:
    stop = tax.weak | {"how", "what", "why", "when", "where", "who", "do", "does", "can", "should", "vs", "versus", "near", "me"}
    agg: dict[str, list] = defaultdict(lambda: [0, 0, []])
    for k in unclassified:
        toks = [t for t in k.tokens if t not in stop and len(t) > 2 and not t.isdigit()]
        grams = set(toks) | {f"{a} {b}" for a, b in zip(toks, toks[1:])}
        for g in grams:
            a = agg[g]
            a[0] += 1
            a[1] += k.volume
            if len(a[2]) < 3:
                a[2].append(k.keyword)
    rows = [[g, a[0], a[1], " | ".join(a[2])] for g, a in agg.items() if a[0] >= 2]
    rows.sort(key=lambda r: (-r[2], -r[1], r[0]))
    return rows[:top]


def write_report(path, args, infos, warnings, total_rows, reasons, n_kept, merged, clusters, cl_rows, unclassified,
                 unclassified_vol, total_vol, groups, dims, elapsed, sim_t, serp_t, argv, respell, n_lexical):
    singles = sum(1 for c in clusters if len(c) == 1)
    fit_vol: Counter = Counter()
    theme_vol: Counter = Counter()
    theme_n: Counter = Counter()
    for r in cl_rows:
        fit_vol[r["blog_fit"]] += r["cluster_volume"]
        theme_vol[r["theme"] or "(none)"] += r["cluster_volume"]
        theme_n[r["theme"] or "(none)"] += 1
    L = ["# Keyword clustering report", ""]
    L += ["## 1. Input", "", "| File | Encoding | Delimiter | Header row | Rows | Recognised columns | Volume source |", "|---|---|---|---:|---:|---|---|"]
    for i in infos:
        cols = ", ".join(f"{k}←{v}" for k, v in i["columns"].items())
        L.append(f"| {os.path.basename(i['path'])} | {i['encoding']} | {i['delimiter']} | {i['header_row']} | {i['rows']:,} | {cols} | {i['volume_source']} |")
    if warnings:
        L += ["", "**Warnings:**"] + [f"- {w}" for w in warnings]
    typos, joins = respell["typos"], respell["joins"]
    splits, completions = respell.get("splits", {}), respell.get("completions", {})
    if typos or joins or splits or completions:
        examples = ([f"{a}→{b}" for a, b in list(typos.items())[:12]] + [f"'{a} {b}'→{j}" for (a, b), j in list(joins.items())[:3]]
                    + [f"{w}→'{a} {b}'" for w, (a, b) in list(splits.items())[:2]]
                    + [f"'{a} {b}'→'{a} {w}'" for (a, b), w in list(completions.items())[:2]])
        L += ["", f"**Spelling fixed from the file itself:** {respell['keywords_changed']:,} keywords changed by "
              f"{len(typos):,} typo corrections, {len(joins):,} joined words, {len(splits):,} split words and "
              f"{len(completions):,} completed cut-off words (e.g. {', '.join(examples)}). "
              "Turn off with `--no-respell` if a correction is wrong."]
    L += ["", "## 2. Filters", "", f"- Read {total_rows:,} rows; kept {n_kept:,} keywords; excluded {sum(reasons.values()):,}."]
    if reasons:
        L += ["", "| Exclusion reason | Keywords |", "|---|---:|"] + [f"| {r} | {n:,} |" for r, n in reasons.most_common()]
        L += ["", "Every excluded keyword is listed in `excluded.csv`. Check it for false exclusions and adjust `assets/noise-rules.json` if a rule is too aggressive."]
    L += ["", "## 3. Clustering result", "",
          f"- {n_kept:,} keywords -> {merged:,} same-meaning variants merged -> {n_lexical:,} lexical clusters -> "
          f"**{len(clusters):,} clusters (posts)** after merging clusters that ask the same thing in other words "
          f"(thresholds: Jaccard {sim_t}, SERP overlap {serp_t} URLs).",
          f"- Single-keyword clusters: {singles:,} ({100 * singles // max(1, len(clusters))}%). "
          "A very high share means the keywords are very diverse or the threshold is too strict: try `--granularity loose`.",
          "- Volume by blog fit: " + ", ".join(f"{k}={fit_vol[k]:,}" for k in ("high", "medium", "low")),
          "- Note: `cluster_volume` is the SUM of the keyword volumes in the cluster, so it is an upper bound (many keywords share the same searchers)."]
    L += ["", "### Top 20 clusters by volume", "", "| Cluster | Keywords | Volume | Need | Fit | Occasion | Recipient | Interest | Theme |", "|---|---:|---:|---|---|---|---|---|---|"]
    for r in cl_rows[:20]:
        L.append(f"| {r['cluster_name']} | {r['keyword_count']} | {r['cluster_volume']:,} | {r['reader_need']} | {r['blog_fit']} | "
                 f"{r['occasion'] or '-'} | {r['recipient'] or '-'} | {r['interest'] or '-'} | {r['theme'] or '-'} |")
    if len(theme_n) > 1:
        L += ["", "### Themes (sub-topics; topic-map uses them to split a pillar that is too big)", "",
              "| Theme | Clusters | Volume |", "|---|---:|---:|"]
        L += [f"| {t} | {theme_n[t]:,} | {v:,} |" for t, v in theme_vol.most_common()]
    if groups:
        L += ["", f"## 4. Groups by {', '.join(dims)}", "", "| Group | Clusters | Keywords | Volume | % |", "|---|---:|---:|---:|---:|"]
        for g in groups[:15]:
            L.append(f"| {g['group']} | {g['clusters']} | {g['keywords']:,} | {g['volume']:,} | {g['volume_share_pct']} |")
    pct = 100 * unclassified_vol / max(1, total_vol)
    L += ["", "## 5. Unclassified", "",
          f"- {len(unclassified):,} keywords matched no facet ({pct:.0f}% of volume). "
          "See `unclassified.csv` and `taxonomy-suggestions.csv` to extend the taxonomy (new niches/occasions).",
          "- If this share is high, the file may be off-topic (filter with `--include/--exclude`) or the taxonomy is missing niches."]
    L += ["", "## 6. Needs review", "", "- `merge-candidates.csv`: cluster pairs near the merge threshold; Claude or the SEO reviews them and merges by hand if needed.",
          "- A `reader_need=info` cluster (medium fit) may be a section of a pillar post rather than a post of its own.",
          "", "## 7. Command run", "", "```", "python3 cluster_keywords.py " + " ".join(argv), "```",
          f"Processing time: {elapsed:.1f}s"]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


# --------------------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="CSV or .xlsx export files; append ::us or ::uk to assign a market to a file")
    ap.add_argument("--request", help="JSON file with the options below (key = option name, use _ instead of -)")
    ap.add_argument("--out", default="outputs")
    ap.add_argument("--market", help="default market for files without a country column (us|uk)")
    ap.add_argument("--map", action="append", metavar="COLUMN=NAME", help="map a column, e.g. keyword='Top queries' volume=Impressions")
    ap.add_argument("--range-mode", choices=["low", "mid", "high"], default="low",
                    help="how to read volume ranges such as '1K - 10K' from Keyword Planner (default: lower bound)")
    ap.add_argument("--granularity", choices=list(GRANULARITY), default="normal",
                    help="cluster size: tight = many small clusters, loose = fewer large clusters")
    ap.add_argument("--sim", type=float, help="Jaccard threshold (overrides granularity)")
    ap.add_argument("--serp-overlap", type=int, help="number of shared top-10 URLs needed to merge (overrides granularity)")
    ap.add_argument("--trust-parent-topic", action="store_true", help="merge by the Ahrefs Parent Topic column")
    ap.add_argument("--group-by", default="none", help="dimension to group the clusters by, e.g. occasion,recipient | interest | intent | category | none")
    ap.add_argument("--top-groups", type=int, default=30)
    ap.add_argument("--only", action="append", metavar="FACET=VALUE", help="keep only keywords with this facet value, e.g. occasion=mothers-day,fathers-day")
    ap.add_argument("--include", action="append", metavar="REGEX", help="keep only keywords matching at least one regex")
    ap.add_argument("--exclude", action="append", metavar="REGEX", help="drop keywords matching the regex")
    ap.add_argument("--min-volume", type=int, default=0)
    ap.add_argument("--max-volume", type=int, default=0)
    ap.add_argument("--max-kd", type=float)
    ap.add_argument("--drop-shop", action="store_true", help="drop pure shopping-intent keywords")
    ap.add_argument("--categories", help="JSON of custom groups: {'Group name': ['word', 'phrase', 're:regex']}")
    ap.add_argument("--taxonomy", help="replace the default taxonomy entirely")
    ap.add_argument("--extend-taxonomy", action="append", help="JSON that extends the taxonomy (new niches or occasions)")
    ap.add_argument("--noise-rules", help="replace the default noise rules file")
    ap.add_argument("--no-noise-filter", action="store_true", help="do not filter noise (retailers, local intent, other languages...)")
    ap.add_argument("--no-respell", action="store_true", help="do not fix typos and split words learned from the file")
    ap.add_argument("--no-consolidate", action="store_true",
                    help="keep lexical clusters as they are (do not merge clusters that ask the same thing in other words)")
    return ap


def parse_args(argv: list[str]):
    ap = build_parser()
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--request")
    known, _ = pre.parse_known_args(argv)
    if known.request:
        with open(known.request, encoding="utf-8") as fh:
            cfg = {k.replace("-", "_"): v for k, v in json.load(fh).items() if not k.startswith("_")}
        valid = {a.dest for a in ap._actions}
        bad = sorted(set(cfg) - valid)
        if bad:
            raise SystemExit(f"--request has invalid keys: {', '.join(bad)}. Valid: {', '.join(sorted(valid - {'help'}))}")
        ap.set_defaults(**cfg)
    args = ap.parse_args(argv)
    if not args.files:
        ap.error("at least one CSV file is required (or a 'files' key in --request)")
    args.files = [args.files] if isinstance(args.files, str) else args.files
    return args


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(argv)
    started = time.time()
    tax = Taxonomy.load(args.taxonomy, args.extend_taxonomy)
    noise = None if args.no_noise_filter else NoiseRules.load(args.noise_rules)
    cats = Categories.load(args.categories) if args.categories else None
    sim_t = args.sim if args.sim is not None else GRANULARITY[args.granularity][0]
    serp_t = args.serp_overlap if args.serp_overlap is not None else GRANULARITY[args.granularity][1]
    dims = [d.strip() for d in args.group_by.split(",") if d.strip() and d.strip() != "none"]
    for d in dims:
        if d not in GROUP_FIELDS:
            raise SystemExit(f"--group-by is invalid: '{d}'. Valid: {', '.join(GROUP_FIELDS)}, none")
    if "category" in dims and not cats:
        raise SystemExit("--group-by category needs --categories file.json")

    kept, excluded, reasons, infos, warnings, total_rows, respell = ingest(args, tax, noise, cats)
    if not kept:
        raise SystemExit("No keywords left after filtering. Reasons: " + ", ".join(f"{r}={n}" for r, n in reasons.most_common(5)))
    n_kept = len(kept)
    rows, merged = dedupe(kept)
    cl = Clusterer(rows, tax.weak, sim_t, serp_t, args.trust_parent_topic)
    lexical = cl.run()
    raw_pairs = cl.merge_candidates()
    if args.no_consolidate:
        clusters, owner = lexical, list(range(len(lexical)))
    else:
        clusters, owner = consolidate(lexical)
    fluency = Fluency(k.keyword for k in kept if not k.fixed)
    clusters = [evergreen_seed(c, fluency) for c in clusters]
    pairs, seen = [], set()
    for s, a, b, why in raw_pairs:  # map pairs onto the consolidated clusters; drop pairs that are now one post
        a, b = owner[a], owner[b]
        if a != b and (min(a, b), max(a, b)) not in seen:
            seen.add((min(a, b), max(a, b)))
            pairs.append((s, a, b, why))
    kw_rows, cl_rows, ids, _ = build_rows(clusters, tax, fluency)

    os.makedirs(args.out, exist_ok=True)
    write_csv(os.path.join(args.out, "keyword-map.csv"), KW_FIELDS, kw_rows)
    write_csv(os.path.join(args.out, "clusters.csv"), CL_FIELDS, cl_rows)
    write_csv(os.path.join(args.out, "excluded.csv"), ["keyword", "volume", "reason", "source_file"],
              sorted(excluded, key=lambda e: -e[1]))
    write_csv(os.path.join(args.out, "merge-candidates.csv"),
              ["cluster_a", "name_a", "cluster_b", "name_b", "score", "reason"],
              [[ids[id(clusters[a])], clusters[a][0].keyword, ids[id(clusters[b])], clusters[b][0].keyword,
                f"{s:.2f}", why] for s, a, b, why in pairs])
    # 'unclassified' = no niche recognised (the theme says what kind of post, not who it is for), so taxonomy
    # suggestions still surface unknown niches such as 'pickleball' in 'gifts for pickleball players'
    unclassified = [k for k in rows if not any(getattr(k, f) for f in FACET_ORDER if f != "theme") and not k.category]
    write_csv(os.path.join(args.out, "unclassified.csv"), ["keyword", "volume", "reader_need"],
              [[k.keyword, k.volume, k.need] for k in sorted(unclassified, key=lambda k: -k.volume)])
    write_csv(os.path.join(args.out, "taxonomy-suggestions.csv"), ["term", "keywords", "volume", "examples"],
              suggest_terms(unclassified, tax))
    groups = []
    if dims:
        groups = build_groups(cl_rows, dims)
        write_groups(args.out, groups, dims, args.top_groups)
    total_vol = sum(k.volume + k.var_vol for k in rows)
    write_report(os.path.join(args.out, "cluster-report.md"), args, infos, warnings, total_rows, reasons, n_kept, merged,
                 clusters, cl_rows, unclassified, sum(k.volume for k in unclassified), total_vol, groups, dims,
                 time.time() - started, sim_t, serp_t, argv, respell, len(lexical))

    fit = Counter(k.fit for k in rows)
    print(f"Read {total_rows:,} rows -> kept {n_kept:,} -> {len(rows):,} after merging variants -> {len(lexical):,} lexical "
          f"clusters -> {len(clusters):,} clusters ({time.time() - started:.1f}s)")
    if respell["typos"] or respell["joins"] or respell["splits"] or respell["completions"]:
        print(f"Spelling fixed from the file: {respell['keywords_changed']:,} keywords "
              f"({len(respell['typos']):,} typos, {len(respell['joins']):,} joined, {len(respell['splits']):,} split, "
              f"{len(respell['completions']):,} completed words)")
    print(f"Excluded {sum(reasons.values()):,} keywords: " + (", ".join(f"{r}={n:,}" for r, n in reasons.most_common(4)) or "none"))
    print("Blog fit: " + ", ".join(f"{k}={fit[k]:,}" for k in ("high", "medium", "low")) +
          f" | unclassified: {len(unclassified):,} | pairs to review: {len(pairs)}")
    for w in warnings:
        print("WARNING:", w, file=sys.stderr)
    print(f"Read cluster-report.md first. Written to: {os.path.abspath(args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
