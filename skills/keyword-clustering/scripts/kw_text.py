#!/usr/bin/env python3
"""Normalise keyword text, detect facets / reader need / category, filter noise.

Shared module for cluster_keywords.py. Standard library only.
"""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "..", "assets")
DEFAULT_TAXONOMY = os.path.join(ASSETS, "taxonomy.json")
DEFAULT_NOISE = os.path.join(ASSETS, "noise-rules.json")

# Facet detection order: occasions and interests are detected first and "masked" so that the recipient is not counted twice
# ("dog mom" -> interest=dogs, recipient=mom). The theme (sub-topic: dates, history, food...) is detected last, on the text
# with only the occasion masked, with its own precedence rules (see Taxonomy.detect_theme).
FACET_ORDER = ["occasion", "interest", "recipient", "product", "style", "craft", "theme"]
IMPLIED_RECIPIENT = {"mothers-day": "mom", "fathers-day": "dad"}
YEAR_RX = re.compile(r"^(19|20)\d\d$")
YEAR_IN_TEXT_RX = re.compile(r"\b(19|20)\d\d\b")
ORDINAL_RX = re.compile(r"^\d+(st|nd|rd|th)$")
# "gifts from daughter" -> the daughter is the giver, not the recipient.
GIVER_RX = re.compile(
    r"\bfrom (?:(?:a|an|the|my|your|our) )?(?:mom|mum|mother|dad|father|daughter|son|kids?|children|wife|"
    r"husband|granddaughter|grandson|grandkids?|girlfriend|boyfriend|sister|brother|friends?|coworkers?|"
    r"team|class|students?)\b")
# "when's" / "whens" -> "when is" (the apostrophe is often dropped in searches)
CONTRACTION_RX = re.compile(r"\b(what|when|where|who|how|that|there)s\b")
# "google when is thanksgiving" / "hey siri what day is thanksgiving" is the same question typed into an assistant
ASSISTANT_PREFIX_RX = re.compile(r"^(?:(?:hey|ok|okay|ask) )?(?:google|alexa|siri|bing|chatgpt)\s+"
                                 r"(?=(?:what|when|where|who|why|how|which|is|are|do|does|did|can)\b)")


# --------------------------------------------------------------------------- text helpers
def collapse_repeats(toks: list[str]) -> list[str]:
    """'thanksgiving thanksgiving thanksgiving' -> 'thanksgiving'; 'labor day labor day' -> 'labor day'."""
    i = 0
    while i < len(toks):
        for size in (3, 2, 1):
            if i + 2 * size <= len(toks) and toks[i:i + size] == toks[i + size:i + 2 * size]:
                del toks[i + size:i + 2 * size]
                break
        else:
            i += 1
    return toks


def normalize_text(s: str) -> str:
    s = s.lower().replace("’", "'").replace("‘", "'").replace("`", "'")
    s = re.sub(r"'s\b", "s", s)
    s = s.replace("'", "")
    s = re.sub(r"[-_/]", " ", s)
    s = re.sub(r"[^\w\s&.]", " ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"\.(?!\d)|(?<!\d)\.", " ", s)  # keep decimals (1.5) but split 'thanksgiving.2025'
    s = CONTRACTION_RX.sub(r"\1 is", s)
    s = ASSISTANT_PREFIX_RX.sub("", s.strip())
    return " ".join(collapse_repeats(s.split()))


def stem(tok: str) -> str:
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 4 and tok.endswith(("ches", "shes", "sses", "xes", "zes")):
        return tok[:-2]
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith(("ss", "us", "is")):
        return tok[:-1]
    return tok


def weighted_jaccard(a: frozenset, b: frozenset, weak: frozenset) -> float:
    """Jaccard with weak tokens ('gift', 'ideas', 'best') weighing 0.3. Weights are summed as integers (10 and 3) so
    the score does not depend on set order: float sums did, and a pair exactly at the threshold flipped between runs."""
    if not a or not b:
        return 0.0
    inter = union = 0
    for t in a | b:
        w = 3 if t in weak else 10
        union += w
        if t in a and t in b:
            inter += w
    return inter / union if union else 0.0


def _alt(patterns: list[str], where: str) -> re.Pattern:
    try:
        return re.compile("|".join(f"(?:{p})" for p in patterns))
    except re.error as exc:
        raise SystemExit(f"Invalid regex in '{where}': {exc}")


def _compile_alternatives(values: dict) -> tuple[re.Pattern | None, list[str]]:
    """Combine all patterns of a facet into one regex so large files can be scanned quickly."""
    parts, keys = [], []
    for i, (key, spec) in enumerate(values.items()):
        alt = _alt(spec["patterns"], key).pattern
        parts.append(f"(?P<g{i}>{alt})")
        keys.append(key)
    return (re.compile("|".join(parts)) if parts else None), keys


def _terms_regex(terms: list[str]) -> re.Pattern:
    if not terms:
        return re.compile(r"(?!)")
    return re.compile("|".join(r"\b" + re.escape(t) + r"\b" for t in terms))


def _match_index(m: re.Match) -> int:
    name = m.lastgroup
    if name and name[0] == "g" and name[1:].isdigit():
        return int(name[1:])
    for name, val in m.groupdict().items():
        if val is not None and name[0] == "g" and name[1:].isdigit():
            return int(name[1:])
    raise RuntimeError("could not determine which group matched")


# --------------------------------------------------------------------------- taxonomy
PATTERN_LISTS = ("patterns", "weak_patterns", "generic")


def merge_taxonomy(base: dict, extra: dict) -> dict:
    """Extend the default taxonomy: add new values, or append patterns to existing values."""
    for facet, spec in extra.get("facets", {}).items():
        tgt = base["facets"].setdefault(facet, {"values": {}})
        for k in ("title_template", "year_only", "product_theme"):
            if k in spec:
                tgt[k] = spec[k]
        for key, val in spec.get("values", {}).items():
            if key in tgt["values"]:
                cur = tgt["values"][key]
                for lk in PATTERN_LISTS:
                    if lk in val:
                        cur[lk] = cur.get(lk, []) + [p for p in val[lk] if p not in cur.get(lk, [])]
                for k, v in val.items():
                    if k not in PATTERN_LISTS:
                        cur[k] = v
            else:
                tgt["values"][key] = val
    for k in ("weak_tokens", "us_only_terms", "uk_only_terms", "core_stopwords"):
        base[k] = list(dict.fromkeys(base.get(k, []) + extra.get(k, [])))
    for k in ("variants", "phrase_variants", "blog_fit", "core_synonyms"):
        base.setdefault(k, {}).update(extra.get(k, {}))
    if extra.get("reader_need_rules_prepend"):
        base["reader_need_rules"] = extra["reader_need_rules_prepend"] + base["reader_need_rules"]
    return base


class Taxonomy:
    def __init__(self, data: dict):
        self.data = data
        self.facets = {f: _compile_alternatives(data["facets"].get(f, {"values": {}})["values"])
                       for f in FACET_ORDER if f != "theme"}
        # a value with 'requires' only applies when that regex matches too (or a product is named): craft=sizing needs
        # a garment or print, so 'turkey size' is not a sizing question
        self.requires = {(f, k): _alt([v["requires"]], f"{f}.{k}.requires")
                         for f in FACET_ORDER if f != "theme"
                         for k, v in data["facets"].get(f, {"values": {}})["values"].items() if v.get("requires")}
        self.need_rx = []
        for rule in data["reader_need_rules"]:
            self.need_rx.append((rule["need"], re.compile("|".join(f"(?:{p})" for p in rule["patterns"]))))
        self.blog_fit = data["blog_fit"]
        self.weak = frozenset(data["weak_tokens"])
        self.variants = data["variants"]
        self.phrase_rx = [(re.compile(r"\b" + re.escape(k) + r"\b"), v)
                          for k, v in sorted(data["phrase_variants"].items(), key=lambda kv: -len(kv[0]))]
        self.us_rx = _terms_regex(data["us_only_terms"])
        self.uk_rx = _terms_regex(data["uk_only_terms"])
        self.seasonal = {k for k, v in data["facets"]["occasion"]["values"].items() if v.get("seasonal")}
        theme = data["facets"].get("theme", {"values": {}})
        tv = theme["values"]
        self.theme_strong = [(k, _alt(v["patterns"], f"theme.{k}")) for k, v in tv.items() if v.get("patterns")]
        self.theme_weak = [(k, _alt(v["weak_patterns"], f"theme.{k}")) for k, v in tv.items() if v.get("weak_patterns")]
        self.theme_generic = {k: _alt(v["generic"], f"theme.{k}") for k, v in tv.items() if v.get("generic")}
        self.theme_need = {k: v.get("need", "") for k, v in tv.items()}
        self.theme_year_only = theme.get("year_only", "")
        self.theme_product = theme.get("product_theme", "")
        self.core_stop = frozenset(data.get("core_stopwords", [])) | self.weak
        self.core_syn = data.get("core_synonyms", {})

    @classmethod
    def load(cls, path: str | None = None, extend: list[str] | None = None) -> "Taxonomy":
        with open(path or DEFAULT_TAXONOMY, encoding="utf-8") as fh:
            data = json.load(fh)
        for extra_path in extend or []:
            with open(extra_path, encoding="utf-8") as fh:
                data = merge_taxonomy(data, json.load(fh))
        return cls(data)

    def phrased(self, norm: str) -> str:
        for rx, repl in self.phrase_rx:
            norm = rx.sub(repl, norm)
        return norm

    def canon_tokens(self, norm: str) -> list[str]:
        out = []
        for tok in self.phrased(norm).split():
            if YEAR_RX.match(tok):
                continue  # "mothers day gifts 2026" ~ "mothers day gifts"
            out.append(stem(self.variants.get(tok, tok)))
        return out

    def mask_occasion(self, norm: str) -> str:
        rx, _ = self.facets["occasion"]
        return rx.sub(lambda m: " " * len(m.group()), norm) if rx is not None else norm

    def detect_facets(self, norm: str) -> dict[str, str]:
        work, out = norm, {}
        occasion_masked = norm
        for facet in FACET_ORDER:
            out[facet] = ""
            if facet == "theme":
                out["theme"] = self.detect_theme(occasion_masked, norm, out)
                continue
            rx, keys = self.facets[facet]
            if rx is None:
                continue
            if facet == "recipient" and " from " in work:
                work = GIVER_RX.sub(lambda m: " " * len(m.group()), work)
            if facet in ("occasion", "interest"):
                matches = list(rx.finditer(work))
                if not matches:
                    continue
                out[facet] = keys[_match_index(matches[0])]
                pieces, last = [], 0
                for m in matches:  # mask every matched span so later facets do not count it again
                    pieces += [work[last:m.start()], " " * (m.end() - m.start())]
                    last = m.end()
                pieces.append(work[last:])
                work = "".join(pieces)
                if facet == "occasion":
                    occasion_masked = work
            else:
                m = rx.search(work)
                if m:
                    key = keys[_match_index(m)]
                    req = self.requires.get((facet, key))
                    if req is None or out.get("product") or req.search(norm):
                        out[facet] = key
        # A seasonal occasion on its own ('thanksgiving', 'thanksgiving day in the states', 'is thanksgiving') is searched
        # for its date first, so it joins the dates theme instead of floating without a theme.
        if (not out["theme"] and out["occasion"] in self.seasonal and self.theme_year_only and not out["product"]
                and not self.core_tokens(norm, "")):
            out["theme"] = self.theme_year_only
        return out

    def detect_theme(self, occasion_masked: str, norm: str, facets: dict) -> str:
        """Strong patterns in taxonomy order (first match wins), then: a product -> product_theme, then weak patterns,
        then an occasion keyword that only adds a year ('thanksgiving 2026') -> year_only."""
        if facets.get("craft"):
            return ""  # know-how about printed products ('how to wash a graphic tee') is not a gift or event sub-topic
        for key, rx in self.theme_strong:
            if rx.search(occasion_masked):
                return key
        if facets.get("product") and self.theme_product:
            return self.theme_product
        for key, rx in self.theme_weak:
            if rx.search(occasion_masked):
                return key
        if facets.get("occasion") and self.theme_year_only and YEAR_IN_TEXT_RX.search(norm):
            return self.theme_year_only
        return ""

    def classify_need(self, norm: str, facets: dict, product_shop: bool = True) -> str:
        """First matching rule; else a keyword that only names a product is 'shop' (product_shop=False skips that
        fallback, used when the tool's intent or the SERP features say the reader wants information)."""
        for need, rx in self.need_rx:
            if rx.search(norm):
                return need
        if facets["product"] and product_shop:
            return "shop"
        if facets.get("theme") and self.theme_need.get(facets["theme"]):
            return self.theme_need[facets["theme"]]
        if facets["occasion"] or facets["recipient"] or facets["interest"]:
            return "inspire"
        return "info"

    def core_tokens(self, norm: str, theme: str) -> frozenset:
        """What a keyword asks once the topic (occasion), the theme's generic words, question words and stop words are
        removed: 'when is thanksgiving' and 'what day is thanksgiving 2026' both give an empty core (the same post),
        'is thanksgiving always on a thursday' gives {thursday}. Synonyms map to one token (true/truth/real -> real)."""
        work = self.mask_occasion(norm)
        if theme in self.theme_generic:
            work = self.theme_generic[theme].sub(" ", work)
        out = set()
        for raw in self.phrased(work).split():
            tok = self.variants.get(raw, raw)
            st = stem(tok)
            syn = self.core_syn.get(tok) or self.core_syn.get(st)
            if syn:
                out.add(syn)
            elif not (tok in self.core_stop or st in self.core_stop or ORDINAL_RX.match(tok) or tok.isdigit()):
                out.add(st)
        return frozenset(out)

    def market_terms(self, norm: str) -> str:
        us, uk = bool(self.us_rx.search(norm)), bool(self.uk_rx.search(norm))
        return "mixed" if us and uk else "us" if us else "uk" if uk else "none"


# --------------------------------------------------------------------------- respelling learned from the file
def _deletes(word: str) -> set[str]:
    return {word[:i] + word[i + 1:] for i in range(len(word))}


INFLECTIONS = {"s", "es", "d", "ed", "ing", "er", "ers", "ly"}


def _is_inflection(a: str, b: str) -> bool:
    """'celebrates' / 'celebrate' or 'veteran' / 'veterans' are word forms, not typos: leave them to the regexes and stem()."""
    short, long_ = sorted((a, b), key=len)
    return long_.startswith(short) and long_[len(short):] in INFLECTIONS


def osa_distance(a: str, b: str, cap: int = 3) -> int:
    """Optimal string alignment distance (edits + adjacent transpositions), stopped early above cap."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if prev2 is not None and i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > cap:
            return cap + 1
        prev2, prev = prev, cur
    return prev[-1]


class Respeller:
    """Typos and split words learned from the whole file, applied before facets and filters:
    'thanksgivng' / 'thankgiving' -> 'thanksgiving', 'thanks giving' -> 'thanksgiving', 'thanksgivi g' -> 'thanksgiving'
    (a space typed inside the word), 'whenis' -> 'when is' (a missing space), 'thanksgiving da' -> 'thanksgiving day'
    (an autocomplete query cut off in its last word).

    Only frequent words (in >= max(30, 0.3% of the keywords)) can be targets, the typo must be at least 10x rarer,
    6+ letters long, within 1 edit (2 for targets of 9+ letters) and share the first or the last letter, so rare
    real words are left alone. Split words are joined only when the joined form is clearly the usual spelling; a rare
    word is split or a cut-off last word completed only when the result is a pair of words the file uses 10x more."""
    MIN_LEN = 6

    def __init__(self, typos: dict[str, str] | None = None, joins: dict[tuple[str, str], str] | None = None,
                 splits: dict[str, tuple[str, str]] | None = None, completions: dict[tuple[str, str], str] | None = None):
        self.typos, self.joins = typos or {}, joins or {}
        self.splits, self.completions = splits or {}, completions or {}

    @classmethod
    def learn(cls, docs: list[list[str]]) -> "Respeller":
        df: Counter = Counter()
        bigrams: Counter = Counter()
        for toks in docs:
            df.update(set(toks))
            bigrams.update(set(zip(toks, toks[1:])))
        joins = {}
        for (a, b), n in bigrams.items():
            joined = a + b
            if len(a) >= 3 and len(b) >= 3 and len(joined) >= 7 and joined.isalpha() and df.get(joined, 0) >= max(20, 3 * n):
                joins[(a, b)] = joined
        min_df = max(30, int(0.003 * len(docs)))
        targets = {t for t, n in df.items() if n >= min_df and len(t) >= cls.MIN_LEN and t.isalpha()}
        index: dict[str, set] = defaultdict(set)
        for t in targets:
            index[t].add(t)
            for d1 in _deletes(t):
                index[d1].add(t)
                if len(t) >= 9:
                    for d2 in _deletes(d1):
                        index[d2].add(t)

        def correct(word: str, n: int) -> str | None:
            cands = set(index.get(word, ()))
            for d1 in _deletes(word):
                cands |= index.get(d1, set())
            best = None
            for t in cands:
                if df[t] < 10 * n or (t[0] != word[0] and t[-1] != word[-1]) or _is_inflection(word, t):
                    continue
                dist = osa_distance(word, t, 2)
                if dist <= (1 if len(t) < 9 else 2) and (best is None or (dist, -df[t], t) < (best[0], -df[best[1]], best[1])):
                    best = (dist, t)
            return best[1] if best else None

        typos = {}
        for word, n in df.items():
            if word in targets or len(word) < cls.MIN_LEN or not word.isalpha():
                continue
            fixed = correct(word, n)
            if fixed:
                typos[word] = fixed
        common = {t for t, n in df.items() if n >= min_df and t.isalpha()}
        rare = max(2, min_df // 10)

        def fragment(x: str) -> bool:  # a stray letter, or a piece almost never used on its own
            return (len(x) == 1 and x not in ("a", "i")) or (len(x) >= 3 and df[x] <= 2 and x not in common)
        # a space typed inside a word: 'thanksgivi g' -> 'thanksgivig' -> 'thanksgiving'. One side must be a fragment and
        # neither side a short real word ('is', 'on', 'vs'), so 'is real' never becomes 'israel'.
        for (a, b), n in bigrams.items():
            if (a, b) in joins or not (a + b).isalpha() or len(a + b) < cls.MIN_LEN or a + b in targets:
                continue
            if not (fragment(a) or fragment(b)) or any(len(x) == 2 or x in ("a", "i") for x in (a, b)):
                continue
            if (a in typos and b in common) or (b in typos and a in common):
                continue  # 'haloween costume': the typo fix is enough, the other word stays
            fixed = correct(a + b, n)
            if fixed and fixed not in (a, b):
                joins[(a, b)] = fixed
        # a missing space: 'whenis' -> 'when is', only for a rare word whose two halves are a common pair of words
        splits = {}
        for word, n in df.items():
            if n > rare or len(word) < 4 or not word.isalpha() or word in typos or word in common:
                continue
            best = max(((bigrams.get((word[:i], word[i:]), 0), word[:i], word[i:]) for i in range(1, len(word))
                        if word[:i] in common and word[i:] in common), default=None)
            if best and best[0] >= max(20, 10 * n):
                splits[word] = (best[1], best[2])
        # an autocomplete query cut off in its last word: 'thanksgiving da' -> 'thanksgiving day', when one completion
        # is by far the most common next word after the previous one
        by_prefix: dict[str, list[str]] = defaultdict(list)
        for w in common:
            for i in range(2, len(w)):
                by_prefix[w[:i]].append(w)
        completions = {}
        for (a, b), n in bigrams.items():
            if df[b] > rare or len(b) < 2 or not b.isalpha() or b not in by_prefix:
                continue
            ranked = sorted(((bigrams.get((a, w), 0), w) for w in by_prefix[b]), reverse=True)
            top = ranked[0][0]
            runner_up = ranked[1][0] if len(ranked) > 1 else 0
            if top >= max(20, 10 * n) and top >= 3 * runner_up:
                completions[(a, b)] = ranked[0][1]
        return cls(typos, joins, splits, completions)

    def apply(self, norm: str, trace: list | None = None) -> str:
        """The corrected text. trace (a list) receives every fix applied: (kind, from, to) with kind in typo, join,
        split, completion (written to spelling-fixes.csv)."""
        if not (self.typos or self.joins or self.splits or self.completions):
            return norm
        toks, out, i = norm.split(), [], 0
        while i < len(toks):
            if i + 1 < len(toks) and (toks[i], toks[i + 1]) in self.joins:
                out.append(self.joins[(toks[i], toks[i + 1])])
                if trace is not None:
                    trace.append(("join", f"{toks[i]} {toks[i + 1]}", out[-1]))
                i += 2
            elif toks[i] in self.splits:
                out.extend(self.splits[toks[i]])
                if trace is not None:
                    trace.append(("split", toks[i], " ".join(self.splits[toks[i]])))
                i += 1
            else:
                out.append(toks[i])
                i += 1
        fixed = [self.typos.get(t, t) for t in out]
        if trace is not None:
            trace += [("typo", a, b) for a, b in zip(out, fixed) if a != b]
        if len(out) >= 2:  # only the LAST word can be cut off
            for prev in (out[-2], fixed[-2]):
                if (prev, out[-1]) in self.completions:
                    fixed[-1] = self.completions[(prev, out[-1])]
                    if trace is not None:
                        trace.append(("completion", f"{prev} {out[-1]}", f"{prev} {fixed[-1]}"))
                    break
        return " ".join(fixed)


# --------------------------------------------------------------------------- how natural a phrasing is
class Fluency:
    """A word-pair model learned from the file's own keywords: how usual each step from one word to the next is.
    'true story of thanksgiving' (common pairs: 'true story', 'story of', 'of thanksgiving') scores higher than
    'real story thanksgiving'; 'thanksgiving facts for kids' higher than '... for kindergarteners'. Used only to choose
    between phrasings of one question with similar volume. Score = mean log probability per step (higher = better)."""
    LAMBDA = 0.8

    def __init__(self, phrases):
        self.c1: Counter = Counter()
        self.c2: Counter = Counter()
        for text in phrases:
            toks = ["<s>"] + normalize_text(text).split() + ["</s>"]
            self.c1.update(toks)
            self.c2.update(zip(toks, toks[1:]))
        self.total = sum(self.c1.values()) + len(self.c1)

    def score(self, text: str) -> float:
        toks = ["<s>"] + normalize_text(text).split() + ["</s>"]
        logp = 0.0
        for a, b in zip(toks, toks[1:]):
            pair = self.c2[(a, b)] / self.c1[a] if self.c1[a] else 0.0
            logp += math.log(self.LAMBDA * pair + (1 - self.LAMBDA) * (self.c1[b] + 1) / self.total)
        return logp / (len(toks) - 1)


# --------------------------------------------------------------------------- noise filter
LANGUAGE_RULES = {"spanish_language", "other_language"}


class NoiseRules:
    """Remove keywords that do not belong to the blog scope: retailer/brand navigation, local intent, other languages, too long...
    Every excluded keyword is written to excluded.csv with its reason; nothing is dropped silently."""

    def __init__(self, data: dict):
        self.rules = []
        for rule in data.get("rules", []):
            try:
                rx = re.compile("|".join(f"(?:{p})" for p in rule["patterns"]))
            except re.error as exc:
                raise SystemExit(f"Invalid noise regex in '{rule.get('name')}': {exc}")
            self.rules.append((rule["name"], rule.get("on", "norm"), rx))
        self.max_words = data.get("max_words", 12)
        self.max_chars = data.get("max_chars", 120)
        self.non_ascii_ratio = data.get("non_ascii_ratio", 0.3)

    @classmethod
    def load(cls, path: str | None = None) -> "NoiseRules":
        with open(path or DEFAULT_NOISE, encoding="utf-8") as fh:
            return cls(json.load(fh))

    def check(self, raw_lower: str, norm: str, language_only: bool = False, skip_language: bool = False) -> str | None:
        """First rule that matches, or None. language_only: only the other-language rules (used to keep Spanish words
        out of the spelling fixes, so 'action' is never 'corrected' to 'accion'); skip_language: every other rule
        (used on the respelled text, whose language was already judged on the original words)."""
        if not language_only and (len(raw_lower) > self.max_chars or len(norm.split()) > self.max_words):
            return "too_long"
        letters = [c for c in raw_lower if c.isalpha()]
        if not skip_language and letters and sum(1 for c in letters if ord(c) > 127) / len(letters) > self.non_ascii_ratio:
            return "non_english_script"
        for name, on, rx in self.rules:
            if (language_only and name not in LANGUAGE_RULES) or (skip_language and name in LANGUAGE_RULES):
                continue
            if rx.search(raw_lower if on == "raw" else norm):
                return name
        return None


# --------------------------------------------------------------------------- custom categories
class Categories:
    """Groups defined by the SEO specialist: {"Group name": ["word", "phrase", "re:regex"]}.
    Plain words get word boundaries and an optional plural automatically; use the prefix re: for a raw regex."""

    def __init__(self, data: dict):
        self.names, self.rx = [], []
        for name, terms in data.items():
            if name.startswith("_"):
                continue
            parts = []
            for t in terms:
                if t.startswith("re:"):
                    parts.append(f"(?:{t[3:]})")
                else:
                    parts.append(r"\b" + re.escape(normalize_text(t)) + r"s?\b")
            self.names.append(name)
            self.rx.append(re.compile("|".join(parts)))

    @classmethod
    def load(cls, path: str) -> "Categories":
        with open(path, encoding="utf-8") as fh:
            return cls(json.load(fh))

    def assign(self, norm: str) -> tuple[str, list[str]]:
        hits = [n for n, rx in zip(self.names, self.rx) if rx.search(norm)]
        return (hits[0] if hits else ""), hits
