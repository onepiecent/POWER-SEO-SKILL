#!/usr/bin/env python3
"""SERP To-do and SERP Check sheets of the final plan (module of export_plan.py; standard library only).

Checking every keyword on the live SERP costs time (and tokens when Claude reads the pages), and most checks only
confirm what the rules already decided. So the skill picks the few that can change the plan:

  SERP To-do   keywords to look up on Google before the plan is final, at most --serp-budget (default 25), from the
               pairs the rules could not decide: possible duplicates of the SEO's groups (seo-audit.csv, tone words
               on a product topic: 'cute trio halloween costumes' vs 'trio halloween costumes'), groups the topic map
               merged as the same subject (seo-audit-topic.csv) and, for a raw export, serp-check.csv. A pair counts
               only when the smaller side has --serp-min-volume searches (default 100: below that it is a section of
               a post whatever the SERP says). Keywords are picked pair by pair, the biggest decision first, and one
               lookup serves every pair of that keyword ('trio halloween costumes' once for 4 pairs). Keywords with
               SERP data already (--serp) are skipped. Each row has the Google URL to open (gl/hl of the market).
  SERP Check   every pair of checked keywords (--serp) that ask nearly the same words: shared top-10 URLs, the
               verdict (>= --serp-overlap: one post, else two posts) and where both are in the plan now (STT), so the
               editor sees each verdict and that the plan follows it [Google: the live SERP; Convention: threshold 4].
               A pair gets a row when the rules compared it, when its SERPs share enough URLs, or when one keyword's
               words are inside the other's (or they share >= 60% of their words).

serp.csv: one row per result, columns keyword, url and optionally market, position, title, checked_at, source (what
assets/serp-extract.js copies from a Google results page), or one row per keyword with serp_urls. keyword-clustering
reads the same file with --serp (run_plan.py passes it to both steps).
"""
from __future__ import annotations

import csv
import io
import re
import urllib.parse
from collections import defaultdict

import table_io
from plan_audit import Where, _key
from plan_decisions import decision_key, norm_market

TODO_COLUMNS = ["#", "Market", "Keyword", "Volume", "Now in Plan (STT)", "Decides", "Google URL", "Checked"]
TODO_WIDTHS = [5, 8, 42, 9, 12, 90, 60, 10]
CHECK_COLUMNS = ["Market", "Keyword A", "Volume A", "Keyword B", "Volume B", "Shared Top-10", "Verdict",
                 "A in Plan (STT)", "B in Plan (STT)", "Plan Follows", "Shared URLs", "Checked"]
CHECK_WIDTHS = [8, 40, 9, 40, 9, 12, 26, 12, 12, 12, 80, 22]
GOOGLE = {"us": "https://www.google.com/search?q={q}&gl=us&hl=en",
          "uk": "https://www.google.co.uk/search?q={q}&gl=uk&hl=en-GB"}
TOP = 10
CLOSE_WORDS = 0.6   # checked keywords this close in words (or one inside the other) get a row in SERP Check
WORD_RX = re.compile(r"[a-z0-9]+")


def norm_url(u: str) -> str:
    u = re.sub(r"^https?://(www\.)?", "", (u or "").strip().lower())
    return re.split(r"[?#]", u)[0].rstrip("/")


def _rows(path: str) -> list[dict]:
    """The SERP file as dicts with lowercase keys: an .xlsx sheet 'SERP' (else the first with a keyword column), or a
    CSV whose delimiter is the header line's (titles contain commas and '|')."""
    if path.lower().endswith((".xlsx", ".xlsm")):
        try:
            rows = table_io.read_table(path, {"keyword"}, sheet="SERP")
        except SystemExit:
            rows = table_io.read_table(path, {"keyword"})
    else:
        with open(path, "rb") as fh:
            raw = fh.read()
        text = next((raw.decode(e) for e in ("utf-8-sig", "utf-16", "cp1252") if _decodes(raw, e)), "")
        first = next((ln for ln in text.splitlines() if "keyword" in ln.lower()), "")
        rows = list(csv.DictReader(io.StringIO(text, newline=""), delimiter=max(",;\t", key=first.count)))
    return [{str(k or "").strip().lower(): str(v or "").strip() for k, v in r.items()} for r in rows]


def _decodes(raw: bytes, enc: str) -> bool:
    try:
        raw.decode(enc)
        return True
    except UnicodeDecodeError:
        return False


def read_serp(paths: list[str]) -> dict[tuple, dict]:
    """{(market, decision key): {'keyword', 'urls' (top 10, in order), 'checked_at', 'source'}}; a row without a
    market applies to every market (key ''). The latest checked_at of a keyword wins."""
    out: dict[tuple, dict] = {}
    for path in paths:
        got: dict[tuple, list] = defaultdict(list)
        meta: dict[tuple, tuple] = {}
        for m, r in enumerate(_rows(path)):
            kw = r.get("keyword") or r.get("query", "")
            if not kw:
                continue
            key = (norm_market(r.get("market") or r.get("country", "")), decision_key(kw), r.get("checked_at", ""))
            meta.setdefault(key, (kw, r.get("source", "")))
            if r.get("url"):
                try:
                    pos = int(float(r.get("position") or 0)) or 1000 + m
                except ValueError:
                    pos = 1000 + m
                if pos <= TOP or pos >= 1000:
                    got[key].append((pos, norm_url(r["url"])))
            else:
                for i, u in enumerate(x for x in re.split(r"[|\s]+", r.get("serp_urls", "")) if x):
                    got[key].append((i + 1, norm_url(u)))
        for (market, k, date), results in sorted(got.items(), key=lambda kv: kv[0][2]):
            urls = list(dict.fromkeys(u for _, u in sorted(results) if u))[:TOP]
            if urls:
                out[(market, k)] = {"keyword": meta[(market, k, date)][0], "urls": urls, "checked_at": date,
                                    "source": meta[(market, k, date)][1]}
    return out


def serp_of(serp: dict, market: str, kw: str) -> dict | None:
    k = decision_key(kw)
    return serp.get((market, k)) or serp.get(("", k))


def _words(kw: str) -> set[str]:
    return {w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in WORD_RX.findall(kw.lower())}


def candidate_pairs(audits: list[dict], checks: list[dict], volume_of) -> list[dict]:
    """The pairs the rules left to the SERP: {'market', 'a' (the smaller side), 'b', 'va', 'vb', 'why'}, one per
    unordered pair."""
    out, seen = [], set()

    def add(market: str, a: str, va, b: str, vb, why: str) -> None:
        if not a or not b or _key(a) == _key(b):
            return
        key = (market, frozenset((_key(a), _key(b))))
        if key in seen:
            return
        seen.add(key)
        va, vb = _int(va, volume_of(market, a)), _int(vb, volume_of(market, b))
        if va > vb:
            a, va, b, vb = b, vb, a, va
        out.append({"market": market, "a": a, "va": va, "b": b, "vb": vb, "why": why})
    for r in audits:
        if r.get("check") == "possible_duplicate":
            add(r.get("market", ""), r.get("keyword", ""), r.get("keyword_volume"), r.get("target_main", ""), None,
                "possible duplicate of the SEO's groups (cluster step)")
        elif r.get("check") == "same_subject" and r.get("step") == "topic":
            add(r.get("market", ""), r.get("keyword", ""), r.get("keyword_volume"), r.get("target_main", ""), None,
                "merged by the topic map as the same subject (angle words such as 'easy', 'best' set aside)")
    for r in checks:
        add(norm_market(r.get("market", "")), r.get("keyword_a", ""), r.get("volume_a"), r.get("keyword_b", ""),
            r.get("volume_b"), r.get("why") or "near the merge threshold (serp-check.csv)")
    return out


def _int(v, default) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return int(default or 0)


def todo_rows(plan, topic: list[dict], keywords: list[dict] | None, audits: list[dict], checks: list[dict],
              serp: dict, budget: int, min_volume: int) -> list[list]:
    where = Where(plan, topic, keywords)
    vol: dict[tuple, int] = {}
    for k in keywords or []:
        vol.setdefault((k.get("market", ""), _key(k.get("keyword"))), _int(k.get("volume"), 0))
    for r in topic:
        vol.setdefault((r.get("market", ""), _key(r.get("cluster_name"))), _int(r.get("seed_volume"), 0))

    def volume_of(market: str, kw: str) -> int:
        return vol.get((market, _key(kw)), 0)
    pairs = [p for p in candidate_pairs(audits, checks, volume_of) if p["va"] >= min_volume]
    pairs.sort(key=lambda p: (-p["va"], -p["vb"], p["a"]))
    chosen: dict[tuple, dict] = {}
    for p in pairs:
        need = [(p["market"], kw, v) for kw, v in ((p["b"], p["vb"]), (p["a"], p["va"]))
                if serp_of(serp, p["market"], kw) is None and (p["market"], _key(kw)) not in chosen]
        if len(chosen) + len(need) > budget:
            continue
        for market, kw, v in need:
            chosen[(market, _key(kw))] = {"market": market, "keyword": kw, "volume": v, "pairs": [], "weight": 0}
        for kw in (p["a"], p["b"]):
            c = chosen.get((p["market"], _key(kw)))
            if c is not None:
                other = p["b"] if kw == p["a"] else p["a"]
                c["pairs"].append(f"vs '{other}' ({p['vb'] if kw == p['a'] else p['va']:,}): {p['why']}")
                c["weight"] += p["va"]
    out = []
    for i, c in enumerate(sorted(chosen.values(), key=lambda c: (-c["weight"], -c["volume"], c["keyword"])), 1):
        n, _ = where.of_keyword(c["keyword"], c["market"])
        url = GOOGLE.get(c["market"], GOOGLE["us"]).format(q=urllib.parse.quote_plus(c["keyword"]))
        out.append([i, c["market"], c["keyword"], c["volume"], n if n is not None else "", "; ".join(c["pairs"]), url,
                    ""])
    return out


def check_rows(plan, topic: list[dict], keywords: list[dict] | None, audits: list[dict], checks: list[dict],
               serp: dict, overlap: int) -> list[list]:
    """One row per pair of checked keywords that the rules compared or that ask nearly the same words."""
    if not serp:
        return []
    where = Where(plan, topic, keywords)
    vol: dict[tuple, int] = {}
    for k in keywords or []:
        vol.setdefault((k.get("market", ""), _key(k.get("keyword"))), _int(k.get("volume"), 0))
    entries = list(serp.items())
    pairs = {(p["market"], frozenset((_key(p["a"]), _key(p["b"])))) for p in
             candidate_pairs(audits, checks, lambda m, kw: vol.get((m, _key(kw)), 0))}
    out = []
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            (ma, ka), ea = entries[i]
            (mb, kb), eb = entries[j]
            if ma and mb and ma != mb:
                continue
            market = ma or mb
            a, b = ea["keyword"], eb["keyword"]
            wa, wb = _words(a), _words(b)
            close = wa <= wb or wb <= wa or len(wa & wb) / max(1, len(wa | wb)) >= CLOSE_WORDS
            shared = [u for u in ea["urls"] if u in set(eb["urls"])]
            if not close and len(shared) < overlap and (market, frozenset((_key(a), _key(b)))) not in pairs:
                continue
            n_a, _ = where.of_keyword(a, market)
            n_b, _ = where.of_keyword(b, market)
            together = n_a is not None and n_a == n_b
            one = len(shared) >= overlap
            verdict = f"one post (>= {overlap} shared)" if one else "two posts"
            if n_a is None or n_b is None:
                follows = "not in plan"
            else:
                follows = "yes" if together == one else ("no: merged" if together else "no: apart")
            out.append([market, a, vol.get((market, _key(a)), ""), b, vol.get((market, _key(b)), ""),
                        f"{len(shared)}/{min(len(ea['urls']), len(eb['urls']))}", verdict,
                        n_a if n_a is not None else "", n_b if n_b is not None else "", follows,
                        " | ".join(shared), "; ".join(sorted({x for x in (ea["checked_at"], eb["checked_at"]) if x}))])
    out.sort(key=lambda r: (r[9] == "yes", -_int(r[2], 0), r[1], r[3]))
    return out
