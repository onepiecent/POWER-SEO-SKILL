#!/usr/bin/env python3
"""Decisions for the cluster step (data contracts C1-C3), a module of cluster_keywords.py. Standard library only.

The scripts compute the evidence; Claude or the SEO makes the judgment calls in a decisions file, each with a reason and
the evidence used; this module applies them deterministically on every run and logs every one of them.

Decisions file: a CSV, or an .xlsx whose sheet 'Decisions' (else its first sheet) has the headers
    decision_id, action, market, keyword, target, value, reason, evidence, source_issue, author, date
Cluster-step actions, in the order they are applied:
    drop_keyword, keep_keyword  at ingest; keep_keyword bypasses the noise, volume, KD, regex and --drop-shop filters,
                                not --only
    merge                       keyword = a member of the surviving post, target = a member of the absorbed post
    move_keyword                keyword (with its variants) -> the post that contains target
    split                       keyword = the new main, value = 'a|b|c' members that go with it
    keep_apart                  keyword and target end in different posts (the one that is not the main leaves)
    rename_main                 keyword becomes its post's main
    set_need                    value = the reader need of the keyword and of its post's main
Within one action, decisions run in decision_id order. Actions of the other steps (topic-map, export) are ignored here
and not logged. Log: decisions-log-cluster.csv with decision_id, step, action, market, keyword, target, value, author,
status, detail; status is applied, applied_with_warning, already_true, rejected_by_data, stale, invalid or conflict.
A Claude-authored merge / move_keyword / keep_apart / split contradicted by the data (both sides have SERP URLs and share
fewer than --serp-overlap of them, or at least that many for keep_apart / split; or different Parent Topics for merge /
move_keyword) is rejected_by_data; a human one is applied_with_warning (the SEO may have checked the live SERP).
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict

from kw_ingest import _xlsx_rows, _xlsx_sheets, _xlsx_shared_strings, decode_bytes, is_xlsx, norm_market
from kw_text import normalize_text

DECISION_FIELDS = ["decision_id", "action", "market", "keyword", "target", "value", "reason", "evidence",
                   "source_issue", "author", "date"]
LOG_FIELDS = ["decision_id", "step", "action", "market", "keyword", "target", "value", "author", "status", "detail"]
STATUSES = ("applied", "applied_with_warning", "already_true", "rejected_by_data", "stale", "invalid", "conflict")
STEP = "cluster"
INGEST_ACTIONS = ("drop_keyword", "keep_keyword")
CLUSTER_ORDER = ("merge", "move_keyword", "split", "keep_apart", "rename_main", "set_need")
CLUSTER_ACTIONS = frozenset(INGEST_ACTIONS + CLUSTER_ORDER)
OTHER_STEPS = frozenset({"set_pillar", "promote_pillar", "demote_pillar", "restore_backlog", "drop_post",  # topic-map
                         "set_category", "set_title", "set_meta", "set_outline", "set_angle", "research_seed"})  # export
PAIR_ACTIONS = ("merge", "move_keyword", "keep_apart")  # the ones that need a target
LIST_NEEDS = ("inspire", "choose")
TOOL_INFO = frozenset({"informational", "commercial"})
QUOTES = str.maketrans({"‘": "'", "’": "'", "‛": "'", "′": "'", "“": '"', "”": '"',
                        "‟": '"', "″": '"'})


def decision_key(text) -> str:
    """The matching key of the data contract: NFC, lowercase, curly quotes made straight, apostrophes removed, '-' and
    '_' to spaces, whitespace collapsed."""
    s = unicodedata.normalize("NFC", str(text or "")).lower().translate(QUOTES).replace("'", "")
    return re.sub(r"\s+", " ", re.sub(r"[-_]", " ", s)).strip()


def id_order(d: dict) -> tuple:
    """decision_id in natural order (D2 before D10)."""
    return tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in re.split(r"(\d+)", d["decision_id"]) if p)


# --------------------------------------------------------------------------- reading
def _head(cell) -> str:
    return re.sub(r"[\s\-]+", "_", unicodedata.normalize("NFC", str(cell or "")).replace("﻿", "").strip().lower())


def _sheet_rows(path: str) -> list[list[str]]:
    if is_xlsx(path):
        with zipfile.ZipFile(path) as zf:
            sheets = [(name, p) for name, p in _xlsx_sheets(zf) if p in zf.namelist()]
            if not sheets:
                raise SystemExit(f"--decisions {path}: the workbook has no readable sheet")
            _, sheet = next((s for s in sheets if s[0].strip().lower() == "decisions"), sheets[0])
            return list(_xlsx_rows(zf, sheet, _xlsx_shared_strings(zf)))
    with open(path, "rb") as fh:
        text, _ = decode_bytes(fh.read())
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    return list(csv.reader(io.StringIO(text, newline=""), delimiter=max(",;\t", key=first.count)))


def read_decisions(path: str) -> list[dict]:
    """The rows of the decisions file as dicts with the contract columns (a missing column is empty) and '_row'. The
    header is the first row, among the first 10, that has decision_id and action."""
    rows = _sheet_rows(path)
    for n, cells in enumerate(rows[:10]):
        heads = [_head(c) for c in cells]
        if "decision_id" in heads and "action" in heads:
            break
    else:
        raise SystemExit(f"--decisions {path}: no header row with decision_id and action in the first 10 rows. "
                         f"Expected columns: {', '.join(DECISION_FIELDS)}")
    col = {h: i for i, h in reversed(list(enumerate(heads))) if h}  # the first of two equal headers wins
    out = []
    for m, cells in enumerate(rows[n + 1:], n + 2):
        if not any(str(c).strip() for c in cells):
            continue
        d = {f: (str(cells[col[f]]) if f in col and col[f] < len(cells) else "").strip() for f in DECISION_FIELDS}
        d["_row"] = m
        out.append(d)
    return out


# --------------------------------------------------------------------------- finding keywords
def _unique(kws: list) -> list:
    return list({id(k): k for k in kws}.values())


class KeyIndex:
    """Keywords by decision key (the keyword and, after dedupe, its variants), with normalize_text as a fallback."""

    def __init__(self, items: list, variants: bool):
        self.items = items
        self.key: dict[tuple, list] = defaultdict(list)
        self.norm: dict[tuple, list] = defaultdict(list)
        for k in items:
            more = k.variants if variants else ()
            for t in (k.keyword, *more):
                self.key[(k.market, decision_key(t))].append(k)
            self.norm[(k.market, k.norm)].append(k)
            for t in more:
                self.norm[(k.market, normalize_text(t))].append(k)
        self.markets = sorted({k.market for k in items})
        self._tok = None

    def find(self, market: str, text: str) -> list:
        return _unique(self.key.get((market, decision_key(text))) or self.norm.get((market, normalize_text(text))) or [])

    def found_in(self, text: str) -> set:
        return {mk for mk in self.markets if self.find(mk, text)}

    def closest(self, text: str, market: str = "") -> str:
        """The current keyword that shares the most words with text (then the larger volume), so a stale decision
        can be re-keyed."""
        if self._tok is None:
            self._tok = defaultdict(list)
            for i, k in enumerate(self.items):
                for w in set(decision_key(k.keyword).split()):
                    self._tok[w].append(i)
        score: Counter = Counter()
        for w in set(decision_key(text).split()):
            for i in self._tok.get(w, ()):
                if not market or self.items[i].market in (market, "all"):
                    score[i] += 1
        if not score:
            return "no current keyword shares a word with it"
        best = min(score, key=lambda i: (-score[i], -self.items[i].volume, self.items[i].keyword))
        k, n = self.items[best], score[best]
        return f"closest: '{k.keyword}' ({k.market}, {n} shared word{'s' * (n != 1)})"


def _best(kws: list):
    return max(kws, key=lambda k: (k.volume, k.keyword))


def _tidy(cl: list) -> None:
    cl[1:] = sorted(cl[1:], key=lambda r: (-(r.volume + r.var_vol), r.keyword))


# --------------------------------------------------------------------------- applying
class ClusterDecisions:
    """The cluster-step decisions of one file: validated on load, applied by at_ingest() / apply(), logged by
    log_rows(). Every logged decision ends with exactly one status."""

    def __init__(self, rows: list[dict], blog_fit: dict):
        self.blog_fit = blog_fit
        self.items: list[dict] = []
        seen: set = set()
        for d in rows:
            d["action"] = d["action"].strip().lower()
            dup = bool(d["decision_id"]) and d["decision_id"] in seen
            seen.add(d["decision_id"])
            if d["action"] in OTHER_STEPS:
                continue
            d.update(status="", detail="", _market=norm_market(d["market"]) if d["market"] else "")
            self.items.append(d)
            problem = "duplicate decision_id" if dup else self.problem(d)
            if problem:
                self.done(d, "invalid", problem)

    def problem(self, d: dict) -> str:
        a = d["action"]
        if not d["decision_id"]:
            return f"decision_id is empty (row {d['_row']})"
        if a not in CLUSTER_ACTIONS:
            return ((f"unknown action '{a}'" if a else "action is empty") + "; cluster-step actions: "
                    + ", ".join(INGEST_ACTIONS + CLUSTER_ORDER))
        empty = [f for f in ("reason", "evidence") if not d[f]]
        if empty:
            return " and ".join(empty) + " empty: every decision states its reason and the evidence used"
        if not d["keyword"]:
            return "keyword is empty"
        if a in PAIR_ACTIONS and not d["target"]:
            return f"{a} needs a target"
        if d["market"] and d["_market"] not in ("us", "uk", "all"):
            return f"market '{d['market']}' is not us, uk or blank"
        if a == "set_need" and d["value"].strip().lower() not in self.blog_fit:
            return f"value '{d['value']}' is not a reader need ({', '.join(self.blog_fit)})"
        return ""

    @staticmethod
    def done(d: dict, status: str, detail: str = "") -> None:
        d["status"], d["detail"] = status, detail

    @staticmethod
    def mark(d: dict, *kws, joined: bool = False) -> None:
        for k in kws:
            if d["decision_id"] not in k.decision_ids:
                k.decision_ids = k.decision_ids + (d["decision_id"],)
            if joined:
                k.joined = f"decision:{d['decision_id']}"

    def pending(self, action: str) -> list[dict]:
        return sorted((d for d in self.items if d["action"] == action and not d["status"]), key=id_order)

    def resolve(self, d: dict, index: KeyIndex, names: list[str], excluded: dict | None = None) -> list | None:
        """[the keywords each name points to] in ONE market, or None once the decision is marked stale or invalid.
        A blank market must resolve to exactly one market; US and UK are never mixed (clustered separately)."""
        found = [index.found_in(t) for t in names]
        for role, t, f in zip(("keyword", "target"), names, found):
            if not f:
                why = f"{role} '{t}' is not in the data"
                if excluded and decision_key(t) in excluded:
                    why = f"{role} '{t}' was excluded ({excluded[decision_key(t)]})"
                self.done(d, "stale", f"{why}; {index.closest(t, d['_market'])}")
                return None
        common = set.intersection(*found)
        given = d["_market"]
        if given:
            mk = given if given in common else "all" if common == {"all"} else ""
        elif len(common) > 1:
            self.done(d, "invalid", f"market is blank and '{names[0]}' is in {' and '.join(sorted(common))}: set the market")
            return None
        else:
            mk = next(iter(common), "")
        if not mk:
            where = "; ".join(f"'{t}' is in {'/'.join(sorted(f))}" for t, f in zip(names, found))
            self.done(d, "invalid", f"markets differ: {where}" + (f" (decision market {given})" if given else "")
                      + "; US and UK are clustered separately")
            return None
        d["_market"] = mk
        return [index.find(mk, t) for t in names]

    # ---- at ingest: drop_keyword / keep_keyword
    def at_ingest(self, rows: list) -> dict:
        """{id(row): (action, decision)} for drop_keyword / keep_keyword on the joined rows. A drop and a keep of the
        same keyword are both a conflict (neither applied)."""
        decs = sorted(self.pending("drop_keyword") + self.pending("keep_keyword"), key=id_order)
        if not decs:
            return {}
        index = KeyIndex(rows, variants=False)
        hits: dict[int, list] = defaultdict(list)
        for d in decs:
            found = self.resolve(d, index, [d["keyword"]])
            if found:
                d["_rows"] = found[0]
                for r in found[0]:
                    hits[id(r)].append(d)
        for ds in hits.values():
            if len({d["action"] for d in ds}) > 1:
                ids = ", ".join(sorted({d["decision_id"] for d in ds}))
                for d in ds:
                    self.done(d, "conflict", f"drop_keyword and keep_keyword on '{d['keyword']}' ({ids}); none applied")
        forced = {}
        for rid, ds in hits.items():
            ds = [d for d in ds if d["status"] != "conflict"]
            if ds:
                forced[rid] = (ds[0]["action"], ds[0])
        for d in decs:
            if d["action"] == "drop_keyword" and not d["status"] and "_rows" in d:
                ids = sorted({forced[id(r)][1]["decision_id"] for r in d["_rows"] if id(r) in forced})
                self.done(d, "applied", f"{len(d['_rows'])} keyword(s) excluded from the plan (excluded.csv, reason "
                                        + ", ".join(f"decision:{i}" for i in ids) + ")")
        return forced

    @staticmethod
    def rescued(d: dict, reason: str) -> None:
        """keep_keyword overrode a filter that would have excluded the keyword."""
        d.setdefault("_rescued", []).append(reason)

    def kept(self, d: dict, k) -> None:
        d["_kept"] = True
        self.mark(d, k)

    def finish_ingest(self) -> None:
        for d in self.pending("keep_keyword"):
            if not d.get("_kept"):
                self.done(d, "stale", "outside this run's --only scope (keep_keyword does not override --only)"
                          if d.get("_scope") else "the keyword did not reach clustering")
            elif d.get("_rescued"):
                detail = "kept despite " + ", ".join(sorted(set(d["_rescued"])))
                warn = [r.keyword for r in d.get("_rows", ()) if r.branded or "navigational" in r.intents]
                if warn:
                    detail += "; warning: the tool marks it branded or navigational"
                self.done(d, "applied_with_warning" if warn else "applied", detail)
            else:
                self.done(d, "already_true", "no filter excluded it in this run")

    # ---- after clustering: merge, move_keyword, split, keep_apart, rename_main, set_need
    def apply(self, clusters: list[list], serp_t: int, reseed, excluded: list | None = None) -> list[list]:
        """Apply the structural decisions to the clusters (lists of KW, main first) and return the clusters left.
        reseed(cluster) names a cluster again after it lost its main (the engine's evergreen rule)."""
        todo = {a: self.pending(a) for a in CLUSTER_ORDER}
        if not any(todo.values()):
            return clusters
        index = KeyIndex([k for cl in clusters for k in cl], variants=True)
        ex: dict = {}
        for kw, _, reason, _ in excluded or ():
            ex.setdefault(decision_key(kw), reason)
        for action, ds in todo.items():
            for d in ds:
                names = [d["keyword"], d["target"]] if action in PAIR_ACTIONS else [d["keyword"]]
                found = self.resolve(d, index, names, ex)
                if found is None:
                    continue
                d["_kw"] = [_best(f) for f in found]
                if action in PAIR_ACTIONS and d["_kw"][0] is d["_kw"][1]:
                    self.done(d, "invalid", "keyword and target are the same keyword")
                elif action == "split":
                    members, missing = [], []
                    for t in (x.strip() for x in d["value"].split("|")):
                        f = index.find(d["_market"], t) if t else None
                        if f:
                            members.append(_best(f))
                        elif t:
                            missing.append(f"'{t}' ({index.closest(t, d['_market'])})")
                    d["_members"] = [m for m in _unique(members) if m is not d["_kw"][0]]
                    d["_missing"] = missing
        where = {id(k): cl for cl in clusters for k in cl}
        self.conflicts(todo, where)
        out = list(clusters)
        for action in CLUSTER_ORDER:
            for d in todo[action]:
                if not d["status"]:
                    getattr(self, "_" + action)(d, where, out, serp_t, reseed)
        return [cl for cl in out if cl]

    def conflicts(self, todo: dict, where: dict) -> None:
        """Opposite effects on the same pair (together: merge, move_keyword, split; apart: keep_apart), the same keyword
        moved to two posts, or two reader needs for one keyword: all of them are a conflict, none applied."""
        live = {a: [d for d in ds if not d["status"]] for a, ds in todo.items()}
        together, apart = defaultdict(list), defaultdict(list)
        for d in live["merge"] + live["move_keyword"]:
            together[frozenset(map(id, d["_kw"]))].append(d)
        for d in live["split"]:
            for m in d["_members"]:
                together[frozenset((id(d["_kw"][0]), id(m)))].append(d)
        for d in live["keep_apart"]:
            apart[frozenset(map(id, d["_kw"]))].append(d)
        groups = [together[p] + apart[p] for p in together.keys() & apart.keys()]
        moves, needs = defaultdict(list), defaultdict(list)
        for d in live["move_keyword"]:
            moves[id(d["_kw"][0])].append(d)
        groups += [ds for ds in moves.values() if len({id(where[id(d["_kw"][1])]) for d in ds}) > 1]
        for d in live["set_need"]:
            needs[id(d["_kw"][0])].append(d)
        groups += [ds for ds in needs.values() if len({d["value"].strip().lower() for d in ds}) > 1]
        for ds in groups:
            ids = ", ".join(sorted({d["decision_id"] for d in ds}, key=lambda i: id_order({"decision_id": i})))
            for d in ds:
                self.done(d, "conflict", f"opposite effects on the same keywords ({ids}); none applied")

    @staticmethod
    def contradiction(action: str, a, b, serp_t: int) -> str:
        """Why the SERP or the Parent Topic contradicts putting a and b in one post (merge, move_keyword) or in two
        posts (keep_apart, split); empty when the data does not contradict it or is missing."""
        ov = len(a.urls & b.urls) if a.urls and b.urls else None
        if action in ("merge", "move_keyword"):
            if ov is not None and ov < serp_t:
                return f"SERP: '{a.keyword}' and '{b.keyword}' share {ov} URLs (below --serp-overlap {serp_t})"
            if a.parent and b.parent and a.parent != b.parent:
                return f"Parent Topics differ: '{a.keyword}' -> {a.parent}, '{b.keyword}' -> {b.parent}"
        elif ov is not None and ov >= serp_t:
            return (f"SERP: '{a.keyword}' and '{b.keyword}' share {ov} URLs (at or above --serp-overlap {serp_t}), "
                    "so the SERP treats them as one post")
        return ""

    def verdict(self, d: dict, warn: str) -> str | None:
        """The status to apply with, or None when a Claude-authored decision is contradicted (rejected_by_data)."""
        if not warn:
            return "applied"
        if d["author"].strip().lower() == "claude":
            self.done(d, "rejected_by_data", warn + "; not applied (author claude)")
            return None
        return "applied_with_warning"

    def finish(self, d: dict, status: str, effect: str, warn: str = "") -> None:
        self.done(d, status, effect + (f"; warning: {warn}" if warn else ""))

    @staticmethod
    def take(k, where: dict, reseed) -> str:
        """Remove k from its post; a post that loses its main is named again by the engine's rule. Returns the name
        the post had."""
        cl = where.pop(id(k))
        name, was_main = cl[0].keyword, cl[0] is k
        cl.remove(k)
        if cl and was_main:
            cl.sort(key=lambda r: (-r.volume, r.keyword))
            reseed(cl)
            _tidy(cl)
        return name

    def _merge(self, d, where, out, serp_t, reseed):
        a, b = d["_kw"]
        A, B = where[id(a)], where[id(b)]
        if A is B:
            self.mark(d, a, b)
            return self.done(d, "already_true", f"already one post: '{A[0].keyword}'")
        warn = self.contradiction("merge", A[0], B[0], serp_t)
        status = self.verdict(d, warn)
        if not status:
            return
        effect = f"'{B[0].keyword}' ({len(B)} keyword{'s' * (len(B) != 1)}) merged into '{A[0].keyword}'"
        self.mark(d, a)
        self.mark(d, *B, joined=True)
        for r in B:
            where[id(r)] = A
        A.extend(B)
        B.clear()
        _tidy(A)
        self.finish(d, status, effect, warn)

    def _move_keyword(self, d, where, out, serp_t, reseed):
        k, t = d["_kw"]
        S, T = where[id(k)], where[id(t)]
        if S is T:
            self.mark(d, k)
            return self.done(d, "already_true", f"'{k.keyword}' is already in '{T[0].keyword}'")
        warn = self.contradiction("move_keyword", k, T[0], serp_t)
        status = self.verdict(d, warn)
        if not status:
            return
        old = self.take(k, where, reseed)
        T.append(k)
        where[id(k)] = T
        _tidy(T)
        self.mark(d, k, joined=True)
        self.finish(d, status, f"'{k.keyword}' moved from '{old}' to '{T[0].keyword}'", warn)

    def _split(self, d, where, out, serp_t, reseed):
        k, members, missing = d["_kw"][0], d["_members"], d["_missing"]
        C = where[id(k)]
        new = {id(k), *map(id, members)}
        if C[0] is k and {id(r) for r in C} == new:
            self.mark(d, k, *members)
            return self.done(d, "already_true", f"'{k.keyword}' is already the main of a post with exactly these keywords")
        rest = [r for r in C if id(r) not in new]
        other = C[0] if C[0] is not k else (max(rest, key=lambda r: (r.volume, r.keyword)) if rest else None)
        warn = self.contradiction("split", k, other, serp_t) if other is not None else ""
        status = self.verdict(d, warn)
        if not status:
            return
        old = C[0].keyword
        for r in (k, *members):
            self.take(r, where, reseed)
        N = [k, *sorted(members, key=lambda r: (-(r.volume + r.var_vol), r.keyword))]
        for r in N:
            where[id(r)] = N
        out.append(N)
        self.mark(d, *N, joined=True)
        if missing:
            warn = "; ".join(filter(None, [warn, "not found: " + ", ".join(missing)]))
            status = "applied_with_warning"
        self.finish(d, status, f"'{k.keyword}' left '{old}' as the main of a new post with {len(members)} other "
                               f"keyword(s)", warn)

    def _keep_apart(self, d, where, out, serp_t, reseed):
        a, b = d["_kw"]
        A, B = where[id(a)], where[id(b)]
        if A is not B:
            self.mark(d, a, b)
            return self.done(d, "already_true", f"already in different posts: '{A[0].keyword}' and '{B[0].keyword}'")
        warn = self.contradiction("keep_apart", a, b, serp_t)
        status = self.verdict(d, warn)
        if not status:
            return
        leaver = a if A[0] is b else b  # the post keeps its main
        old = self.take(leaver, where, reseed)
        N = [leaver]
        where[id(leaver)] = N
        out.append(N)
        self.mark(d, a, b)
        self.mark(d, leaver, joined=True)
        self.finish(d, status, f"'{leaver.keyword}' left '{old}' as a post of its own", warn)

    def _rename_main(self, d, where, out, serp_t, reseed):
        k = d["_kw"][0]
        C = where[id(k)]
        self.mark(d, k)
        if C[0] is k:
            return self.done(d, "already_true", f"'{k.keyword}' is already the main")
        old = C[0].keyword
        C.remove(k)
        C.insert(0, k)
        _tidy(C)
        bigger = max(C, key=lambda r: (r.volume, r.keyword))
        info = (f"; info: '{bigger.keyword}' has more volume ({bigger.volume:,} vs {k.volume:,})"
                if bigger.volume > k.volume else "")
        self.done(d, "applied", f"'{k.keyword}' replaces '{old}' as the main{info}")

    def _set_need(self, d, where, out, serp_t, reseed):
        k = d["_kw"][0]
        seed = where[id(k)][0]
        need = d["value"].strip().lower()
        self.mark(d, k, seed)
        if seed.need == need and k.need == need:
            return self.done(d, "already_true", f"the reader need of '{seed.keyword}' is already {need}")
        intents = seed.intents | k.intents
        warn = ""
        if need == "shop" and intents & TOOL_INFO:
            warn = f"the tool intent is {'+'.join(sorted(intents & TOOL_INFO))}"
        elif need != "shop" and intents and intents <= {"transactional", "navigational"}:
            warn = f"the tool intent is only {'+'.join(sorted(intents))}"
        old = seed.need
        for r in _unique([seed, k]):
            r.need, r.fit, r.need_src = need, self.blog_fit[need], "decision"
            r.ngroup = "list" if need in LIST_NEEDS else need
        self.finish(d, "applied_with_warning" if warn else "applied",
                    f"reader need of '{seed.keyword}' set to {need} (was {old})", warn)

    def decided(self) -> dict:
        """issue_id -> decision_id for the back-check issues a decision settled (its source_issue column; several ids
        are separated by '|', ',', ';' or spaces)."""
        return {iid: d["decision_id"] for d in self.items
                if d["status"] in ("applied", "applied_with_warning", "already_true")
                for iid in re.split(r"[\s|,;]+", d.get("source_issue") or "") if iid}

    # ---- log
    def log_rows(self) -> list[dict]:
        return [{"decision_id": d["decision_id"], "step": STEP, "action": d["action"],
                 "market": d["_market"] or d["market"], "keyword": d["keyword"], "target": d["target"],
                 "value": d["value"], "author": d["author"], "status": d["status"] or "stale",
                 "detail": d["detail"] or "not reached: no keyword left to apply it to"} for d in self.items]

    def summary(self) -> str:
        n = Counter(r["status"] for r in self.log_rows())
        return ("Decisions (cluster step): " + ", ".join(f"{n[s]} {s.replace('_', ' ')}" for s in STATUSES)
                + " -> decisions-log-cluster.csv")
