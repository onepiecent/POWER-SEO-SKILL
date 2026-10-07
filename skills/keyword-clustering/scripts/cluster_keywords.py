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
          <out>/spelling-fixes.csv    every spelling fix learned from the file (to veto a wrong one)
          <out>/serp-check.csv        the pairs and word-only groups the SEO should check on the live SERP

Two levels: CLUSTER (keywords with the same search intent -> one post), then GROUP (--group-by: groups the clusters
along the dimension you ask for: occasion, recipient, interest, product, style, craft, category, intent...).

How clusters are formed:
  * Typos and split words are fixed first, learned from the file itself (thanksgivng, thanks giving -> thanksgiving).
  * Both keywords have serp_urls -> same cluster when >= --serp-overlap URLs overlap.
  * Otherwise                    -> weighted Jaccard on tokens >= --sim.
  * Facet guard: occasion, recipient (including implied), interest, product and theme must match before a lexical merge.
  * Then clusters that ask the same thing in other words are merged into one post: same guard and the same core
    ('when is thanksgiving' = 'what day is thanksgiving 2026' = 'thanksgiving 2026 date'). --no-consolidate turns it off.
  * Each market (us/uk) is clustered separately because the SERPs differ; rows of other markets are excluded.
  * The same keyword from several files or rows is one keyword (the best volume is kept, not the sum).
  * Large files are sped up with an inverted index + prefix filter, so pairs are not compared one by one.
  * Every keyword records how it joined its cluster (joined_by) and every cluster what its grouping rests on
    (grouping_basis); tool intent and SERP features are kept as evidence next to the regex reader need.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kw_evidence import (INFO_FEATURES, is_kp_bucketed, kp_bucket_range, kp_bucket_value, parse_intent,  # noqa: E402
                         parse_serp_features, parse_trend, peak_month, trend_header_range, vendor, ym_add)
from kw_backcheck import write_backcheck  # noqa: E402
from kw_ingest import ALIASES, norm_market, parse_number, read_tables  # noqa: E402
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
MAX_PAIRS = 300
GROUP_COLUMNS = ("group", "main", "secondary", "pillar", "role")  # a file that was already grouped
COLUMN_USE = {  # what each recognised column feeds (cluster-report.md, 'Columns used as evidence')
    "keyword": "keyword", "volume": "volume (priority order, filters, cluster volume)",
    "impressions": "volume fallback: impressions, NOT search volume", "clicks": "volume fallback: clicks, NOT search volume",
    "kd": "KD (`--max-kd`, `kd`, `kd_source`)", "cpc": "CPC (passed through)",
    "market": "market per row (US/UK split; other markets excluded)", "serp": "SERP URLs (clusters by shared URLs)",
    "intent": "tool intent (`intents`; need vs intent check)", "parent": "Parent Topic (merge hint; `--trust-parent-topic`)",
    "position": "ranking position (`position`)", "serp_features": "SERP features (`serp_features`; need vs intent check)",
    "trend": "trend (`trend`; exact months only when the header names them)",
    "traffic_potential": "traffic potential (`traffic_potential`)", "ranking_url": "ranking URL (`ranking_url`)",
    "flag": "tool intent flag (`intents`, `intent_branded`, `intent_local`)",
}
SCOPE_MARKETS = ("us", "uk", "all")  # the blog serves US and UK; 'all' = the file names no market
GSC_ROW_CAP = 1000  # Search Console UI exports stop at 1,000 rows [Google]
TOOL_INFO_INTENTS = frozenset({"informational", "commercial"})  # a reader who researches, not one who buys now


class KW:
    __slots__ = ("keyword", "tokens", "tokset", "volume", "vol_est", "kd", "cpc", "market", "urls", "occasion",
                 "recipient", "interest", "product", "style", "craft", "theme", "core", "need", "fit", "terms",
                 "category", "variants", "var_vols", "var_vol", "parent", "intent_src", "src", "ngroup", "fixed",
                 # evidence from the export and how the keyword was placed
                 "norm", "vclass", "sources", "kd_src", "vol_range", "intents", "branded", "local", "serp_feats",
                 "trend", "trend_scale", "trend_end", "monthly", "tp", "rank_url", "position", "prior", "joined",
                 "need_src", "decision_ids")

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


def file_market(info: dict, suffix: str, default_market: str) -> tuple[str, str]:
    """The market of rows without a market cell, and where it came from (stated in the report): the ::market suffix,
    then the tool's file name, then the Search Console Country filter, then --market."""
    if suffix:
        return norm_market(suffix), f"'::{suffix}' suffix"
    if info["filename_market"]:
        return info["filename_market"], f"file name ({info['filename_pattern']})"
    country = (info.get("gsc_filters") or {}).get("country", "")
    if country:
        return norm_market(country), f"Search Console filter Country = {country}"
    if default_market:
        return default_market, "--market"
    return "", "none (market 'all')"


def load_files(args, overrides: dict, default_market: str, warnings: list) -> list[tuple]:
    """[(source label, info, file market, records)], one per table (every sheet of an .xlsx with a keyword column)."""
    loaded = []
    for spec in args.files:
        path, sep, mk = spec.rpartition("::")
        if not sep:
            path, mk = spec, ""
        tables = read_tables(path, overrides)
        for table in tables:
            info = table.info
            src = os.path.basename(path) + (f" [{info['sheet']}]" if len(tables) > 1 else "")
            market, msrc = file_market(info, mk, default_market)
            if "market" in info["columns"]:
                msrc = f"column '{info['columns']['market']}' per row; empty cells: {msrc}"
            elif msrc.startswith("file name") and default_market and market != default_market:
                warnings.append(f"{src}: the file name says market '{market}' but --market is '{default_market}'; the "
                                f"file name was used. Add ::{default_market} to the path if the file name is wrong.")
            info["src"], info["market_source"] = src, msrc
            loaded.append((src, info, market, list(table)))
    return loaded


def read_trend(k: KW, rec: dict, months: list[str], trend_header: str, header_range) -> None:
    """Keyword Planner monthly searches (exact months), else the Trend column (Ahrefs SV trend is anchored by the
    month range in its header; a Semrush Trend is relative and unanchored here)."""
    k.trend, k.trend_scale, k.trend_end, k.monthly = (), "", "", None
    monthly = rec.get("_monthly")
    if monthly:
        vals = {ym: parse_number(monthly.get(ym), integer=True)[0] for ym in months}
        k.monthly = {ym: int(v) for ym, v in vals.items() if v is not None}
        if months and len(k.monthly) == len(months):
            k.trend, k.trend_scale, k.trend_end = tuple(float(k.monthly[ym]) for ym in months), "absolute", months[-1]
        return
    if rec.get("trend"):
        k.trend, k.trend_scale = parse_trend(rec["trend"], trend_header)
        if k.trend and k.trend_scale == "absolute" and header_range:
            start, end = header_range
            if ym_add(start, len(k.trend) - 1) == end:  # the series covers exactly the months the header names
                k.trend_end = end


def join_key(keyword: str) -> str:
    """The keyword as the tool typed it, ignoring only case, spacing and curly quotes. Texts that differ beyond that
    ('when's thanksgiving' / 'when is thanksgiving') are different searches with their own volume: dedupe() keeps them
    as variants of one keyword."""
    s = unicodedata.normalize("NFC", keyword).lower().replace("\u2019", "'").replace("\u2018", "'")
    return re.sub(r"\s+", " ", s).strip()


def join_sources(rows: list[KW]) -> tuple[list[KW], int]:
    """The same keyword in one market from several files, or repeated in one file (a positions export lists a keyword
    once per ranking URL), is ONE keyword, not a sum. Key = market + join_key(text), before respelling.
    Volume: an exact value beats an estimate (a range, a bucket, GSC impressions), then the larger one; KD and trend
    come from the same source when it has them. Intents, SERP features and URLs are united; other fields keep the
    first value in file order. `sources` keeps every tool and value (volume_sources in keyword-map.csv)."""
    best: dict[tuple, KW] = {}
    for r in rows:
        key = (r.market, join_key(r.keyword))
        cur = best.get(key)
        if cur is None:
            best[key] = r
            continue
        win, lose = (r, cur) if (r.vclass, r.volume) > (cur.vclass, cur.volume) else (cur, r)
        if win.kd is None and lose.kd is not None:
            win.kd, win.kd_src = lose.kd, lose.kd_src
        if not win.trend and lose.trend:
            win.trend, win.trend_scale, win.trend_end, win.monthly = lose.trend, lose.trend_scale, lose.trend_end, lose.monthly
        for f in ("cpc", "parent", "intent_src", "tp", "branded", "local"):
            first = getattr(cur, f)
            setattr(win, f, first if first not in (None, "") else getattr(r, f))
        if lose.position is not None and (win.position is None or lose.position < win.position):
            win.position, win.rank_url = lose.position, lose.rank_url or win.rank_url
        win.rank_url = win.rank_url or lose.rank_url
        win.intents, win.serp_feats, win.urls = cur.intents | r.intents, cur.serp_feats | r.serp_feats, cur.urls | r.urls
        win.sources, win.prior = cur.sources + r.sources, cur.prior + r.prior
        win.src = "|".join(dict.fromkeys(cur.src.split("|") + r.src.split("|")))
        best[key] = win
    return list(best.values()), len(rows) - len(best)


def need_conflict(k: KW) -> str:
    labels = sorted(k.intents & TOOL_INFO_INTENTS)
    if labels:
        tools = "/".join(sorted({vendor(t) for t, _, _ in k.sources}))
        return f"conflict: regex shop vs {tools} {'+'.join(labels)}"
    return "conflict: regex shop vs SERP features " + "+".join(sorted(k.serp_feats & INFO_FEATURES))


def spelling_rows(respeller: Respeller, fixes: dict, rows: list[KW]) -> list[dict]:
    """One row per learned fix: how many keywords it changed (with examples and their volume) and how much volume
    the corrected form already has, so a real word taken for a typo (skirts -> shirts) stands out."""
    learned = ([("typo", a, b) for a, b in respeller.typos.items()]
               + [("join", f"{a} {b}", j) for (a, b), j in respeller.joins.items()]
               + [("split", w, f"{a} {b}") for w, (a, b) in respeller.splits.items()]
               + [("completion", f"{a} {b}", f"{a} {w}") for (a, b), w in respeller.completions.items()])
    if not learned:
        return []
    want_pairs = {tuple(to.split()) for kind, _, to in learned if " " in to}
    word_vol: Counter = Counter()
    pair_vol: Counter = Counter()
    for k in rows:  # volume of the keywords that already use the corrected form (as typed)
        toks = k.norm.split()
        for t in set(toks):
            word_vol[t] += k.volume
        for pr in set(zip(toks, toks[1:])) & want_pairs:
            pair_vol[pr] += k.volume
    out = []
    for fx in learned:
        n, examples, vol = fixes.get(fx, (0, [], 0))
        to = fx[2]
        out.append({"kind": fx[0], "from": fx[1], "to": to, "keywords_changed": n, "examples": " | ".join(examples),
                    "from_volume": vol, "to_volume": pair_vol[tuple(to.split())] if " " in to else word_vol[to],
                    "vetoed": ""})
    out.sort(key=lambda r: (-r["keywords_changed"], -r["from_volume"], r["kind"], r["from"]))
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
    warnings: list[str] = []
    total_rows = 0
    loaded = load_files(args, overrides, default_market, warnings)
    infos = [info for _, info, _, _ in loaded]
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
    # Pass 1: one KW per row with the evidence the export carries; rows of markets other than US/UK are excluded.
    pool: list[KW] = []
    for src, info, file_market, records in loaded:
        vsrc, tool, cols = info["volume_source"], info["source_tool"], info["columns"]
        if vsrc == "none":
            warnings.append(f"{src}: no volume/impressions column; every volume is 0, so the priority order is meaningless.")
        elif vsrc != "volume":
            warnings.append(f"{src}: using column '{cols[vsrc]}' as volume; this is NOT search volume. "
                            "Impressions only reflect queries the site was already shown for, not total market demand; "
                            "add volume from Semrush/Ahrefs/Keyword Planner.")
        if tool == "gsc":
            if info["rows"] == GSC_ROW_CAP:
                warnings.append(f"{src}: exactly {GSC_ROW_CAP:,} rows: Search Console UI exports stop there, so the list "
                                "is probably cut off. Use the API or the bulk export for every query.")
            if not (info.get("gsc_filters") or {}).get("country"):
                warnings.append(f"{src}: no Search Console country filter found (no Filters sheet or Filters.csv with a "
                                "Country row), so impressions mix every country. Export with a country filter or add ::us/::uk.")
        grouped = [cols[c] for c in GROUP_COLUMNS if c in cols]
        if grouped:
            warnings.append(f"{src}: grouping columns ({', '.join(grouped)}) are not used yet; the keywords were "
                            "clustered as a raw export and the existing grouping was ignored.")
        months = sorted(ym for _, ym in info["monthly_columns"])
        bucketed = False
        if tool == "gkp" and vsrc == "volume":
            bucketed = is_kp_bucketed([parse_number(r.get("volume"), integer=True)[0] for r in records],
                                      (c for r in records for c in r.get("_monthly", {}).values()))
        info["volume_basis"] = "Keyword Planner bucket values read as ranges" if bucketed else ""
        trend_header = cols.get("trend", "")
        header_range = trend_header_range(trend_header)
        flags = [c for c in cols if c.startswith("flag_")]
        for n, rec in enumerate(records):
            records[n] = None  # free each raw row once read: a large file is not held twice in memory
            total_rows += 1
            raw_kw = re.sub(r"\s+", " ", rec.get("keyword", "")).strip()
            norm0 = normalize_text(raw_kw)
            if not norm0:
                reasons["empty_keyword"] += 1
                continue
            vol_raw = rec.get(vsrc) if vsrc != "none" else None
            vol, est = parse_number(vol_raw, integer=True, range_mode=args.range_mode)
            vrange = ""
            if bucketed and vol is not None:  # [Research: observed in real exports] 5000 = the '1K–10K' bucket
                vrange, vol, est = kp_bucket_range(vol), kp_bucket_value(vol, args.range_mode), True
            elif est:
                vrange = re.sub(r"\s*[-\u2013\u2014]\s*", "–", str(vol_raw).strip())
            k = KW()
            k.keyword, k.norm, k.src = raw_kw, norm0, src
            k.volume, k.vol_est, k.vol_range = (int(vol) if vol is not None else 0), est, vrange
            # rank of the volume when the keyword is joined: exact > estimate > impressions/clicks > empty > no column
            k.vclass = -1 if vsrc == "none" else 0 if vol is None else 1 if vsrc != "volume" else 2 if est else 3
            k.sources = ((tool, None if vol is None else int(vol), est),)
            k.kd = parse_number(rec.get("kd"))[0]
            k.kd_src = tool if k.kd is not None else ""
            k.cpc = parse_number(rec.get("cpc"))[0]
            mk_row = norm_market(rec.get("market")) if rec.get("market") else ""
            k.market = mk_row or file_market or "all"
            k.urls = frozenset(_norm_url(u) for u in re.split(r"[|\s]+", rec.get("serp", "")) if u.strip())
            k.parent = normalize_text(rec.get("parent", "")) if rec.get("parent") else ""
            k.intent_src = rec.get("intent", "")
            k.intents, k.branded, k.local = parse_intent(rec.get("intent"), {f[5:]: rec.get(f) for f in flags})
            k.serp_feats = parse_serp_features(rec.get("serp_features"))
            read_trend(k, rec, months, trend_header, header_range)
            tp = parse_number(rec.get("traffic_potential"), integer=True)[0]
            k.tp = int(tp) if tp is not None else None
            k.rank_url = rec.get("ranking_url", "")
            k.position = parse_number(rec.get("position"))[0]
            k.prior, k.joined, k.need_src, k.decision_ids = (), "", "", ()  # tuples: one shared empty value
            if k.market not in SCOPE_MARKETS:
                reason = f"market:{k.market}"
                reasons[reason] += 1
                excluded.append((raw_kw, k.volume, reason, src))
                continue
            pool.append(k)
        records.clear()
        if info["rows"] == 0:
            warnings.append(f"{src}: no data rows could be read.")
    rows, n_joined = join_sources(pool)
    # Pass 2: spelling, filters, facets and reader need on each distinct keyword.
    respelled = 0
    fixes: dict[tuple, list] = {}
    need_conflicts = 0
    for k in rows:
        trace: list = []
        norm = respeller.apply(k.norm, trace)
        k.fixed = norm != k.norm
        respelled += k.fixed
        for fx in dict.fromkeys(trace):
            f = fixes.setdefault(fx, [0, [], 0])
            f[0] += 1
            f[2] += k.volume
            if len(f[1]) < 3:
                f[1].append(k.keyword)
        low, volume = k.keyword.lower(), k.volume
        reason = None
        if noise is not None:  # language is judged on the original words ('celebracion' is a Spanish marker)
            reason = noise.check(low, k.norm)
            if reason is None and k.fixed:
                reason = noise.check(low, norm, skip_language=True)
        if reason is None and k.vclass >= 0:
            if args.min_volume and volume < args.min_volume:
                reason = "filter:min_volume"
            elif args.max_volume and volume > args.max_volume:
                reason = "filter:max_volume"
        if reason is None and args.max_kd is not None and k.kd is not None and k.kd > args.max_kd:
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
            excluded.append((k.keyword, volume, reason, k.src))
            continue
        facets = tax.detect_facets(norm)
        need = tax.classify_need(norm, facets)
        k.need_src = "rule"
        # Never drop on regex alone: a keyword that is 'shop' only because it names a product stays a blog keyword
        # when the tool says the reader researches (Semrush/Ahrefs intent) or the SERP answers questions.
        if need == "shop" and (k.intents & TOOL_INFO_INTENTS or k.serp_feats & INFO_FEATURES):
            alt = tax.classify_need(norm, facets, product_shop=False)
            if alt != "shop":
                need, k.need_src = alt, need_conflict(k)
                need_conflicts += 1
        category, _ = cats.assign(norm) if cats else ("", [])
        k.tokens = tuple(tax.canon_tokens(norm))
        k.tokset = frozenset(k.tokens)
        k.core = tax.core_tokens(norm, facets["theme"])
        for f in FACET_ORDER:
            setattr(k, f, facets[f])
        k.need, k.fit = need, tax.blog_fit[need]
        k.ngroup = "list" if need in LIST_NEEDS else need
        k.terms = tax.market_terms(norm)
        k.category, k.variants, k.var_vols, k.var_vol = category, [], [], 0
        if only and not _passes_only(k, only):
            reasons["filter:only"] += 1
            excluded.append((k.keyword, volume, "filter:only", k.src))
            continue
        if args.drop_shop and need == "shop":
            reasons["filter:drop_shop"] += 1
            excluded.append((k.keyword, volume, "filter:drop_shop", k.src))
            continue
        kept.append(k)
    respell = {"typos": respeller.typos, "joins": respeller.joins, "splits": respeller.splits,
               "completions": respeller.completions, "keywords_changed": respelled,
               "fixes": spelling_rows(respeller, fixes, rows)}
    stats = {"joined": n_joined, "need_conflicts": need_conflicts}
    return kept, excluded, reasons, infos, warnings, total_rows, respell, stats


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
        self.cap_hits = 0  # posting lists cut at MAX_POSTING: a qualifying pair beyond the cap can be missed
        self.candidates_total = 0

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
                    self.cap_hits += len(lst) > MAX_POSTING
                    cand.update(lst[:MAX_POSTING])
        return cand

    def _serp_counts(self, k: KW) -> Counter:
        counts: Counter = Counter()
        for u in k.urls:
            lst = self.url_index.get(u, ())
            self.cap_hits += len(lst) > MAX_POSTING
            for i in lst[:MAX_POSTING]:
                counts[i] += 1
        return counts

    def find(self, k: KW) -> tuple[int | None, str]:
        """(cluster index, how the keyword joins it: 'serp:<shared URLs>', 'parent' or 'lexical:<similarity>'), or
        (None, '') when it starts a cluster of its own. Linkage = seed: each keyword is compared with the seed (the
        highest-volume keyword) of each cluster, not with every member."""
        best, best_score = None, None
        if self.trust_parent and k.parent:
            i = self.parent_index.get((k.market, k.parent, k.ngroup))
            if i is not None:
                return i, "parent"
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
        if best is None:
            return None, ""
        return best, (f"serp:{best_score[1]}" if best_score[0] == 2 else f"lexical:{best_score[1]:.2f}")

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
            i, r.joined = self.find(r)
            if i is None:
                r.joined = "seed"
                self.clusters.append([r])
                self._register(len(self.clusters) - 1)
            else:
                self.clusters[i].append(r)
        return self.clusters

    def merge_candidates(self, limit: int = MAX_PAIRS) -> list[tuple]:
        """(score, earlier cluster, later cluster, reason, evidence type) for pairs just below a merge threshold;
        candidates_total says how many there were before the cut at `limit`."""
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
                    out.append((s, j, i, f"tokens close together {s:.2f} (merge threshold {self.sim_t})", "lexical"))
            if k.urls:
                for j, c in self._serp_counts(k).items():
                    seed = self.clusters[j][0]
                    if j < i and 2 <= c < self.serp_t and seed.market == k.market:
                        out.append((c / self.serp_t, j, i, f"SERP overlap {c} URLs (threshold {self.serp_t})", "serp"))
            if k.parent:
                j = self.parent_index.get((k.market, k.parent, k.ngroup))
                if j is not None and j < i and not self.trust_parent:
                    out.append((0.5, j, i, f"same Parent Topic: {k.parent}", "parent_topic"))
        out.sort(key=lambda x: -x[0])
        self.candidates_total = len(out)
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
            for r in cl:  # every member of the absorbed cluster joins through the shared core (logged as joined_by)
                r.joined = f"core:{' '.join(sorted(seed.core)) or '-'}"
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
# New columns are only ever appended (data contract): prior_* and decision_ids stay empty until grouped-file input
# and the decisions file exist; the cluster seasonality columns are filled by the seasonality step.
KW_FIELDS = ["cluster_id", "market", "keyword", "volume", "volume_estimated", "kd", "cpc", "is_seed", "reader_need",
             "blog_fit", "occasion", "recipient", "interest", "product", "style", "craft", "theme", "category",
             "market_terms", "parent_topic", "intent_source", "variants", "source_file", "spelling_fixed",
             "variant_volumes",
             "normalized_keyword", "joined_by", "need_source", "prior_group", "prior_main", "prior_role", "prior_pillar",
             "intents", "intent_branded", "intent_local", "serp_features", "traffic_potential", "ranking_url",
             "position", "trend", "trend_end", "peak_month", "volume_range", "volume_sources", "kd_source",
             "decision_ids"]
CL_FIELDS = ["cluster_id", "market", "cluster_name", "keyword_count", "seed_volume", "cluster_volume", "seed_kd",
             "kd_min", "reader_need", "blog_fit", "occasion", "recipient", "interest", "product", "style", "craft",
             "theme", "core", "category", "season", "market_terms", "parent_topic", "keywords", "name_fluency",
             "grouping_basis", "serp_verified_share", "seed_basis", "prior_group", "prior_pillar", "prior_role",
             "intents_mix", "serp_features_main", "traffic_potential_main", "cluster_volume_dedup", "peak_month",
             "ramp_month", "peak_ratio", "seasonality_source", "decision_ids"]
VERIFIED_KINDS = ("serp", "parent_topic")  # membership that rests on the SERP (shared URLs, the tool's Parent Topic)


def kw_volume(r: KW) -> int:
    return r.volume + r.var_vol


def basis_kind(joined: str) -> str:
    head = joined.split(":", 1)[0]
    return {"parent": "parent_topic", "core": "lexical"}.get(head, head)


def grouping_basis(cl: list[KW]) -> str:
    """What the cluster's grouping rests on: single, serp, parent_topic, lexical (not verified by SERP) or mixed."""
    if len(cl) == 1:
        return "single"
    kinds = {basis_kind(r.joined) for r in cl if r.joined != "seed"}
    if kinds == {"lexical"}:
        return "lexical (not verified by SERP)"
    return next(iter(kinds)) if len(kinds) == 1 else "mixed"


def serp_verified_share(cl: list[KW]) -> str:
    """Share of the cluster's volume whose membership rests on SERP evidence; the seed counts once a member is
    verified against it. Empty for a single keyword (nothing to verify)."""
    total = sum(kw_volume(r) for r in cl)
    if len(cl) == 1 or not total:
        return ""
    ok = [r for r in cl if basis_kind(r.joined) in VERIFIED_KINDS]
    if ok:
        ok += [r for r in cl if r.joined == "seed"]
    return f"{sum(kw_volume(r) for r in ok) / total:.2f}"


def seed_basis(cl: list[KW], fluency: Fluency | None) -> str:
    """Why evergreen_seed named the cluster after cl[0] instead of its biggest keyword."""
    seed, top = cl[0], max(cl, key=lambda r: r.volume)
    if seed.volume >= top.volume:
        return "max_volume"
    if YEAR_KW_RX.search(top.keyword) and not YEAR_KW_RX.search(seed.keyword):
        return "evergreen (no year)"
    if top.fixed and not seed.fixed:
        return "spelled correctly"
    if fluency is not None and fluency.score(seed.keyword) > fluency.score(top.keyword):
        return "more natural phrasing"
    return "plain phrasing"


def intents_mix(cl: list[KW]) -> str:
    """Tool intent labels of the members with keyword counts and volume; empty when no member has a label."""
    n: Counter = Counter()
    vol: Counter = Counter()
    for r in cl:
        for label in r.intents or ("no label",):
            n[label] += 1
            vol[label] += kw_volume(r)
    if set(n) <= {"no label"}:
        return ""
    return " | ".join(f"{lab} ({n[lab]} kw, {vol[lab]:,})" for lab in sorted(n, key=lambda x: (x == "no label", -vol[x], x)))


def volume_dedup(cl: list[KW]) -> int:
    """Labelled estimate: a keyword and its close variants that report the SAME volume count once (tools often give one
    grouped figure for close variants); distinct volumes are still added. The plain sum stays in cluster_volume."""
    return sum(sum(set([r.volume, *r.var_vols])) for r in cl)


def fmt_num(v) -> str | int | float:
    return "" if v is None else int(v) if float(v).is_integer() else v


def fmt_trend(r: KW) -> str:
    if not r.trend:
        return ""
    return ",".join(f"{v:.2f}" for v in r.trend) if r.trend_scale == "relative" else ",".join(str(fmt_num(v)) for v in r.trend)


def fmt_flag(v: bool | None) -> str | int:
    return "" if v is None else int(v)


def build_rows(clusters: list[list[KW]], tax: Taxonomy, fluency: Fluency | None = None):
    kw_rows, cl_rows, ids = [], [], {}
    ordered = sorted(clusters, key=lambda c: (-sum(r.volume + r.var_vol for r in c), c[0].keyword))
    for n, cl in enumerate(ordered, 1):
        seed = cl[0]
        cid = f"C{n:04d}"
        ids[id(cl)] = cid
        kds = [r.kd for r in cl if r.kd is not None]
        terms = {r.terms for r in cl} - {"none"}
        for r in cl:  # a list per keyword (KW_FIELDS order), not a dict: keeps a large file's memory down
            row = {"cluster_id": cid, "market": r.market, "keyword": r.keyword, "volume": r.volume,
                   "volume_estimated": int(r.vol_est), "kd": "" if r.kd is None else int(r.kd),
                   "cpc": "" if r.cpc is None else r.cpc, "is_seed": int(r is seed), "reader_need": r.need,
                   "blog_fit": r.fit, "occasion": r.occasion, "recipient": r.recipient,
                   "interest": r.interest, "product": r.product, "style": r.style, "craft": r.craft,
                   "theme": r.theme, "category": r.category, "market_terms": r.terms, "parent_topic": r.parent,
                   "intent_source": r.intent_src, "variants": "|".join(r.variants), "source_file": r.src,
                   "spelling_fixed": int(r.fixed), "variant_volumes": "|".join(str(v) for v in r.var_vols),
                   "normalized_keyword": " ".join(sorted(r.tokens)), "joined_by": r.joined,
                   "need_source": r.need_src, "prior_group": "", "prior_main": "", "prior_role": "",
                   "prior_pillar": "", "intents": "|".join(sorted(r.intents)),
                   "intent_branded": fmt_flag(r.branded), "intent_local": fmt_flag(r.local),
                   "serp_features": "|".join(sorted(r.serp_feats)), "traffic_potential": fmt_num(r.tp),
                   "ranking_url": r.rank_url, "position": fmt_num(r.position), "trend": fmt_trend(r),
                   "trend_end": r.trend_end, "peak_month": peak_month(r.trend, r.trend_end),
                   "volume_range": r.vol_range,
                   "volume_sources": "|".join(f"{t}:{'-' if v is None else ('~' if e else '') + str(v)}"
                                              for t, v, e in r.sources),
                   "kd_source": r.kd_src, "decision_ids": "|".join(r.decision_ids)}
            kw_rows.append([row[f] for f in KW_FIELDS])
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
                        "name_fluency": f"{fluency.score(seed.keyword):.2f}" if fluency else "",
                        "grouping_basis": grouping_basis(cl), "serp_verified_share": serp_verified_share(cl),
                        "seed_basis": seed_basis(cl, fluency), "prior_group": "", "prior_pillar": "", "prior_role": "",
                        "intents_mix": intents_mix(cl), "serp_features_main": "|".join(sorted(seed.serp_feats)),
                        "traffic_potential_main": fmt_num(seed.tp), "cluster_volume_dedup": volume_dedup(cl),
                        "peak_month": "", "ramp_month": "", "peak_ratio": "", "seasonality_source": "",
                        "decision_ids": "|".join(sorted({d for r in cl for d in r.decision_ids}))})
    return kw_rows, cl_rows, ids, ordered


GUARD_NAMES = ("market", "intent group", "occasion", "recipient", "interest", "product", "theme")


def guard_diff(a: KW, b: KW) -> str:
    """The guard fields (part_key) that differ between two seeds, e.g. 'interest: hunting vs -'."""
    return "; ".join(f"{n}: {x or '-'} vs {y or '-'}" for n, x, y in zip(GUARD_NAMES, part_key(a), part_key(b)) if x != y)


def merge_rows(pairs: list[tuple], clusters: list[list[KW]], ids: dict) -> list[list]:
    rows = []
    for s, a, b, why, etype in pairs:
        A, B = clusters[a], clusters[b]
        rows.append([ids[id(A)], A[0].keyword, ids[id(B)], B[0].keyword, f"{s:.2f}", why, etype,
                     sum(map(kw_volume, A)), sum(map(kw_volume, B)), A[0].need, B[0].need, A[0].theme, B[0].theme,
                     " ".join(sorted(A[0].core)), " ".join(sorted(B[0].core)), guard_diff(A[0], B[0]),
                     "|".join(r.keyword for r in A[:15]), "|".join(r.keyword for r in B[:15])])
    return rows


SERP_CHECK_FIELDS = ["market", "keyword_a", "volume_a", "keyword_b", "volume_b", "why", "current_grouping", "question"]


def serp_check_rows(pairs: list[tuple], clusters: list[list[KW]], ids: dict, serp_t: int, limit: int) -> list[dict]:
    """What the SEO should look at on the live SERP, the largest first: pairs just below a merge threshold, and
    clusters grouped by words only (the main keyword against the biggest other member). [Convention: practitioners
    hand-check a share of clusters on the live SERP; nothing here is decided by the script.]"""
    google = {"us": "google.com (US)", "uk": "google.co.uk (UK)"}
    out = []
    for _, a, b, why, _ in pairs:
        A, B = clusters[a], clusters[b]
        q = (f"Do both show >= {serp_t} of the same top-10 URLs on {google.get(A[0].market, 'Google')}? "
             "Yes: one post (merge); no: keep apart.")
        out.append((sum(map(kw_volume, A)) + sum(map(kw_volume, B)),
                    [A[0].market, A[0].keyword, A[0].volume, B[0].keyword, B[0].volume, why,
                     f"separate posts ({ids[id(A)]}, {ids[id(B)]})", q]))
    for cl in clusters:
        if grouping_basis(cl).startswith("lexical") and len(cl) > 1:
            other = max(cl[1:], key=lambda r: (r.volume, r.keyword))
            q = (f"Do both show >= {serp_t} of the same top-10 URLs on {google.get(cl[0].market, 'Google')}? "
                 "Yes: keep together; no: move the keyword or split the post.")
            basis = cl[0].joined if other.joined == "seed" else other.joined  # the main may have joined the seed
            out.append((sum(map(kw_volume, cl)),
                        [cl[0].market, cl[0].keyword, cl[0].volume, other.keyword, other.volume,
                         f"grouped by words only ({basis}); no SERP data", f"same post ({ids[id(cl)]})", q]))
    out.sort(key=lambda x: (-x[0], x[1][1], x[1][3]))
    return [dict(zip(SERP_CHECK_FIELDS, row)) for _, row in out[:limit]]


def coverage(rows: list[KW]) -> list[tuple]:
    """(evidence, keywords with it, total keywords, volume with it, total volume) for the report."""
    checks = [("SERP URLs (serp_urls)", lambda r: r.urls), ("Parent Topic", lambda r: r.parent),
              ("Tool intent", lambda r: r.intents), ("SERP features", lambda r: r.serp_feats),
              ("Trend / monthly searches", lambda r: r.trend), ("Traffic potential", lambda r: r.tp is not None),
              ("Ranking URL", lambda r: r.rank_url), ("Volume is an estimate (range, bucket)", lambda r: r.vol_est)]
    total_n, total_v = len(rows), sum(map(kw_volume, rows))
    return [(name, sum(1 for r in rows if f(r)), total_n, sum(kw_volume(r) for r in rows if f(r)), total_v)
            for name, f in checks]


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


def column_use(canon: str) -> str:
    if canon in GROUP_COLUMNS or canon in ("stt", "status", "url_blog", "category"):
        return "grouped-file column: not used yet (the keywords were clustered as a raw export)"
    return COLUMN_USE.get(canon.split("_")[0] if canon.startswith("flag_") else canon, "recognised; not used yet")


def pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


def write_report(path, args, infos, warnings, total_rows, reasons, n_kept, merged, clusters, cl_rows, unclassified,
                 unclassified_vol, total_vol, groups, dims, elapsed, sim_t, serp_t, argv, respell, n_lexical, ev=None):
    ev = ev or {}
    singles = sum(1 for c in clusters if len(c) == 1)
    fit_vol: Counter = Counter()
    theme_vol: Counter = Counter()
    theme_n: Counter = Counter()
    for r in cl_rows:
        fit_vol[r["blog_fit"]] += r["cluster_volume"]
        theme_vol[r["theme"] or "(none)"] += r["cluster_volume"]
        theme_n[r["theme"] or "(none)"] += 1
    src = lambda i: i.get("src") or os.path.basename(i["path"])  # noqa: E731
    L = ["# Keyword clustering report", ""]
    L += ["## 1. Input", "", "| File | Encoding | Delimiter | Header row | Rows | Recognised columns | Volume source |", "|---|---|---|---:|---:|---|---|"]
    for i in infos:
        cols = ", ".join(f"{k}←{v}" for k, v in i["columns"].items())
        L.append(f"| {src(i)} | {i['encoding']} | {i['delimiter']} | {i['header_row']} | {i['rows']:,} | {cols} | {i['volume_source']} |")
    L += ["", "### Source tool, market and sheets", "",
          "| File | Source tool | Market source | Date in file name | Sheets read | Sheets skipped |", "|---|---|---|---|---|---|"]
    for i in infos:
        skipped = "; ".join(f"{n} ({why})" for n, why in i.get("sheets_skipped", [])) or "-"
        L.append(f"| {src(i)} | {i.get('source_tool', '-')} | {i.get('market_source', '-')} | {i.get('filename_date') or '-'} | "
                 f"{', '.join(i.get('sheets_read', [])) or '-'} | {skipped} |")
    L += ["", "### Columns used as evidence", "", "| File | Column | Used for |", "|---|---|---|"]
    for i in infos:
        L += [f"| {src(i)} | {h} | {column_use(c)} |" for c, h in i["columns"].items()]
        months = i.get("monthly_columns") or []
        if months:
            L.append(f"| {src(i)} | Searches: {months[0][1]} … {months[-1][1]} ({len(months)} columns) | monthly searches "
                     "(trend with exact months; Keyword Planner bucket check) |")
        if i.get("volume_basis"):
            L.append(f"| {src(i)} | {i['columns'].get('volume', 'volume')} | {i['volume_basis']} (every non-empty value is "
                     "0, 50, 500, 5,000… and the monthly columns are empty) [Research: observed in real exports]: "
                     "`volume_estimated=1`, `volume_range` |")
    L += ["", "### Ignored columns", "",
          "Data the file has that was not used. If an important column is listed here, map it with `--map canonical=Column`.",
          "", "| File | Ignored columns |", "|---|---|"]
    for i in infos:
        ign = ", ".join(h + (f" ({why})" if why else "") for h, why in i.get("ignored_columns", [])) or "(none)"
        L.append(f"| {src(i)} | {ign} |")
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
              "Every fix is in `spelling-fixes.csv`; turn them off with `--no-respell` if a correction is wrong."]
    L += ["", "## 2. Filters", "", f"- Read {total_rows:,} rows; kept {n_kept:,} keywords; excluded {sum(reasons.values()):,}."]
    if ev.get("joined"):
        L.append(f"- {ev['joined']:,} duplicate rows joined: the same keyword in the same market in several files or rows "
                 "is one keyword with the best volume (exact before estimated, then the larger), not the sum; every "
                 "value is in `volume_sources`.")
    if reasons:
        L += ["", "| Exclusion reason | Keywords |", "|---|---:|"] + [f"| {r} | {n:,} |" for r, n in reasons.most_common()]
        L += ["", "Every excluded keyword is listed in `excluded.csv`. Check it for false exclusions and adjust `assets/noise-rules.json` if a rule is too aggressive."]
        if any(r.startswith("market:") for r in reasons):
            L.append("Rows of markets other than US and UK (`market:<code>`) are excluded: the blog serves US and UK.")
    L += ["", "## 3. Clustering result", "",
          f"- {n_kept:,} keywords -> {merged:,} same-meaning variants merged -> {n_lexical:,} lexical clusters -> "
          f"**{len(clusters):,} clusters (posts)** after merging clusters that ask the same thing in other words "
          f"(thresholds: Jaccard {sim_t}, SERP overlap {serp_t} URLs).",
          f"- Single-keyword clusters: {singles:,} ({100 * singles // max(1, len(clusters))}%). "
          "A very high share means the keywords are very diverse or the threshold is too strict: try `--granularity loose`.",
          "- Volume by blog fit: " + ", ".join(f"{k}={fit_vol[k]:,}" for k in ("high", "medium", "low")),
          "- Note: `cluster_volume` is the SUM of the keyword volumes in the cluster, so it is an upper bound (many keywords share the same searchers)."]
    if "dedup" in ev:
        L.append(f"- `cluster_volume_dedup` (estimate) counts a keyword and its close variants that report the same volume "
                 f"once (tools often give one figure for close variants): {ev['dedup']:,} in total, next to a sum of "
                 f"{sum(r['cluster_volume'] for r in cl_rows):,}.")
    if ev.get("coverage"):
        L += ["", "### Evidence coverage", "",
              "What the grouping can rest on. SERP URLs and the tool's Parent Topic are SERP evidence; tool intent, SERP "
              "features and trend are hints [Convention: vendor labels]; everything else is word similarity.", "",
              "| Evidence | Keywords | % keywords | Volume | % volume |", "|---|---:|---:|---:|---:|"]
        L += [f"| {name} | {n:,} | {pct(n, tn)} | {v:,} | {pct(v, tv)} |" for name, n, tn, v, tv in ev["coverage"]]
        L += ["", "- Grouping basis of the clusters: " + ", ".join(f"{b} {n:,}" for b, n in ev["basis"].most_common()) + ".",
              f"- SERP-verified share of the volume of multi-keyword clusters: {ev['verified']} (membership that rests on "
              "shared SERP URLs or the tool's Parent Topic; the rest is grouped by words and listed in `serp-check.csv`).",
              "- Linkage: seed. Each keyword is compared with the highest-volume keyword (seed) of each cluster, not with "
              "every member, so two members can be far apart from each other.",
              (f"- Posting-list cap: {ev['cap_hits']:,} look-ups were cut at {MAX_POSTING:,} entries, so a qualifying pair "
               "beyond the cap may have been missed (a very common token)." if ev.get("cap_hits") else
               f"- Posting-list cap ({MAX_POSTING:,} entries) never hit: no pair that meets the threshold was missed."),
              (f"- `merge-candidates.csv`: the {MAX_PAIRS} strongest of {ev['pairs_total']:,} pairs were kept (cap hit)."
               if ev.get("pairs_total", 0) > MAX_PAIRS else f"- `merge-candidates.csv`: {ev.get('pairs', 0):,} pairs (no cap hit).")]
        if ev.get("need_conflicts"):
            L.append(f"- Need vs tool intent: {ev['need_conflicts']:,} keywords are 'shop' by the regex only because they name "
                     "a product, while the tool intent or the SERP features say the reader researches; they stay in the "
                     "blog plan with `need_source` = conflict (review them).")
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
    upct = 100 * unclassified_vol / max(1, total_vol)
    L += ["", "## 5. Unclassified", "",
          f"- {len(unclassified):,} keywords matched no facet ({upct:.0f}% of volume). "
          "See `unclassified.csv` and `taxonomy-suggestions.csv` to extend the taxonomy (new niches/occasions).",
          "- If this share is high, the file may be off-topic (filter with `--include/--exclude`) or the taxonomy is missing niches."]
    L += ["", "## 6. Needs review", "", "- `merge-candidates.csv`: cluster pairs near the merge threshold, with each side's volume, "
          "need, theme, core, keywords and the guard fields that differ; Claude or the SEO reviews them and merges by hand if needed.",
          f"- `serp-check.csv`: {ev.get('serp_checks', 0):,} pairs and word-only groups, largest first, to check on the live "
          "SERP (the script cannot see Google; a web search is not a Google SERP).",
          f"- `spelling-fixes.csv`: all {len(respell.get('fixes', [])):,} spelling fixes with the keywords they changed and the "
          "volume of each form; a real word taken for a typo (skirts→shirts) has a sizeable `from_volume`.",
          "- Keywords with `need_source` = conflict in `keyword-map.csv`: the regex and the tool disagree on the reader need.",
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
    ap.add_argument("--serp-check-max", type=int, default=30,
                    help="rows in serp-check.csv: the largest pairs and word-only groups to check on the live SERP "
                         "(default 30, a [Convention] review budget)")
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

    kept, excluded, reasons, infos, warnings, total_rows, respell, stats = ingest(args, tax, noise, cats)
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
    for s, a, b, why, etype in raw_pairs:  # map pairs onto the consolidated clusters; drop pairs that are now one post
        a, b = owner[a], owner[b]
        if a != b and (min(a, b), max(a, b)) not in seen:
            seen.add((min(a, b), max(a, b)))
            pairs.append((s, a, b, why, etype))
    kw_rows, cl_rows, ids, _ = build_rows(clusters, tax, fluency)
    checks = serp_check_rows(pairs, clusters, ids, serp_t, args.serp_check_max)

    os.makedirs(args.out, exist_ok=True)
    write_csv(os.path.join(args.out, "keyword-map.csv"), KW_FIELDS, kw_rows)
    write_csv(os.path.join(args.out, "clusters.csv"), CL_FIELDS, cl_rows)
    write_csv(os.path.join(args.out, "excluded.csv"), ["keyword", "volume", "reason", "source_file"],
              sorted(excluded, key=lambda e: -e[1]))
    write_csv(os.path.join(args.out, "merge-candidates.csv"),
              ["cluster_a", "name_a", "cluster_b", "name_b", "score", "reason", "evidence_type", "volume_a", "volume_b",
               "need_a", "need_b", "theme_a", "theme_b", "core_a", "core_b", "guard_diff", "keywords_a", "keywords_b"],
              merge_rows(pairs, clusters, ids))
    write_csv(os.path.join(args.out, "spelling-fixes.csv"),
              ["kind", "from", "to", "keywords_changed", "examples", "from_volume", "to_volume", "vetoed"], respell["fixes"])
    write_csv(os.path.join(args.out, "serp-check.csv"), SERP_CHECK_FIELDS, checks)
    # back-check of the grouping (the SEO's groups, or the engine's clusters in raw mode); proposals are never applied
    backcheck_line = write_backcheck(args.out, kw_rows, cl_rows, {(k.market, k.keyword): k.urls for c in clusters
                                                                  for k in c if k.urls}, serp_t, sim_t, KW_FIELDS)
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
    multi = [c for c in clusters if len(c) > 1]
    multi_vol = sum(kw_volume(r) for c in multi for r in c)
    verified = sum(float(serp_verified_share(c) or 0) * sum(map(kw_volume, c)) for c in multi)
    ev = {**stats, "coverage": coverage(rows), "basis": Counter(r["grouping_basis"] for r in cl_rows),
          "verified": pct(verified, multi_vol) if multi else "- (no multi-keyword cluster)", "cap_hits": cl.cap_hits,
          "pairs_total": cl.candidates_total, "pairs": len(pairs), "serp_checks": len(checks),
          "dedup": sum(r["cluster_volume_dedup"] for r in cl_rows)}
    write_report(os.path.join(args.out, "cluster-report.md"), args, infos, warnings, total_rows, reasons, n_kept, merged,
                 clusters, cl_rows, unclassified, sum(k.volume for k in unclassified), total_vol, groups, dims,
                 time.time() - started, sim_t, serp_t, argv, respell, len(lexical), ev)

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
    print(backcheck_line)
    print(f"Read cluster-report.md first. Written to: {os.path.abspath(args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
