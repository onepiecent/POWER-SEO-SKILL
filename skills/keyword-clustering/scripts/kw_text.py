#!/usr/bin/env python3
"""Normalise keyword text, detect facets / reader need / category, filter noise.

Shared module for cluster_keywords.py. Standard library only.
"""
from __future__ import annotations

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "..", "assets")
DEFAULT_TAXONOMY = os.path.join(ASSETS, "taxonomy.json")
DEFAULT_NOISE = os.path.join(ASSETS, "noise-rules.json")

# Facet detection order: occasions and interests are detected first and "masked" so that the recipient is not counted twice
# ("dog mom" -> interest=dogs, recipient=mom).
FACET_ORDER = ["occasion", "interest", "recipient", "product", "style", "craft"]
IMPLIED_RECIPIENT = {"mothers-day": "mom", "fathers-day": "dad"}
YEAR_RX = re.compile(r"^(19|20)\d\d$")
# "gifts from daughter" -> the daughter is the giver, not the recipient.
GIVER_RX = re.compile(
    r"\bfrom (?:(?:a|an|the|my|your|our) )?(?:mom|mum|mother|dad|father|daughter|son|kids?|children|wife|"
    r"husband|granddaughter|grandson|grandkids?|girlfriend|boyfriend|sister|brother|friends?|coworkers?|"
    r"team|class|students?)\b")


# --------------------------------------------------------------------------- text helpers
def normalize_text(s: str) -> str:
    s = s.lower().replace("’", "'").replace("‘", "'").replace("`", "'")
    s = re.sub(r"'s\b", "s", s)
    s = s.replace("'", "")
    s = re.sub(r"[-_/]", " ", s)
    s = re.sub(r"[^\w\s&.]", " ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"\.(?!\d)", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def stem(tok: str) -> str:
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 4 and tok.endswith(("ches", "shes", "sses", "xes", "zes")):
        return tok[:-2]
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith(("ss", "us", "is")):
        return tok[:-1]
    return tok


def weighted_jaccard(a: frozenset, b: frozenset, weak: frozenset) -> float:
    if not a or not b:
        return 0.0
    inter = union = 0.0
    for t in a | b:
        w = 0.3 if t in weak else 1.0
        union += w
        if t in a and t in b:
            inter += w
    return inter / union if union else 0.0


def _compile_alternatives(values: dict) -> tuple[re.Pattern | None, list[str]]:
    """Combine all patterns of a facet into one regex so large files can be scanned quickly."""
    parts, keys = [], []
    for i, (key, spec) in enumerate(values.items()):
        try:
            alt = "|".join(f"(?:{p})" for p in spec["patterns"])
            re.compile(alt)
        except re.error as exc:
            raise SystemExit(f"Invalid regex in '{key}': {exc}")
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
def merge_taxonomy(base: dict, extra: dict) -> dict:
    """Extend the default taxonomy: add new values, or append patterns to existing values."""
    for facet, spec in extra.get("facets", {}).items():
        tgt = base["facets"].setdefault(facet, {"values": {}})
        if "title_template" in spec:
            tgt["title_template"] = spec["title_template"]
        for key, val in spec.get("values", {}).items():
            if key in tgt["values"]:
                cur = tgt["values"][key]
                cur["patterns"] = cur["patterns"] + [p for p in val.get("patterns", []) if p not in cur["patterns"]]
                for k, v in val.items():
                    if k != "patterns":
                        cur[k] = v
            else:
                tgt["values"][key] = val
    for k in ("weak_tokens", "us_only_terms", "uk_only_terms"):
        base[k] = list(dict.fromkeys(base.get(k, []) + extra.get(k, [])))
    for k in ("variants", "phrase_variants", "blog_fit"):
        base.setdefault(k, {}).update(extra.get(k, {}))
    if extra.get("reader_need_rules_prepend"):
        base["reader_need_rules"] = extra["reader_need_rules_prepend"] + base["reader_need_rules"]
    return base


class Taxonomy:
    def __init__(self, data: dict):
        self.data = data
        self.facets = {f: _compile_alternatives(data["facets"].get(f, {"values": {}})["values"]) for f in FACET_ORDER}
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

    @classmethod
    def load(cls, path: str | None = None, extend: list[str] | None = None) -> "Taxonomy":
        with open(path or DEFAULT_TAXONOMY, encoding="utf-8") as fh:
            data = json.load(fh)
        for extra_path in extend or []:
            with open(extra_path, encoding="utf-8") as fh:
                data = merge_taxonomy(data, json.load(fh))
        return cls(data)

    def canon_tokens(self, norm: str) -> list[str]:
        text = norm
        for rx, repl in self.phrase_rx:
            text = rx.sub(repl, text)
        out = []
        for tok in text.split():
            if YEAR_RX.match(tok):
                continue  # "mothers day gifts 2026" ~ "mothers day gifts"
            out.append(stem(self.variants.get(tok, tok)))
        return out

    def detect_facets(self, norm: str) -> dict[str, str]:
        work, out = norm, {}
        for facet in FACET_ORDER:
            rx, keys = self.facets[facet]
            out[facet] = ""
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
            else:
                m = rx.search(work)
                if m:
                    out[facet] = keys[_match_index(m)]
        return out

    def classify_need(self, norm: str, facets: dict) -> str:
        for need, rx in self.need_rx:
            if rx.search(norm):
                return need
        if facets["product"]:
            return "shop"
        if facets["occasion"] or facets["recipient"] or facets["interest"]:
            return "inspire"
        return "info"

    def market_terms(self, norm: str) -> str:
        us, uk = bool(self.us_rx.search(norm)), bool(self.uk_rx.search(norm))
        return "mixed" if us and uk else "us" if us else "uk" if uk else "none"


# --------------------------------------------------------------------------- noise filter
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

    def check(self, raw_lower: str, norm: str) -> str | None:
        if len(raw_lower) > self.max_chars or len(norm.split()) > self.max_words:
            return "too_long"
        letters = [c for c in raw_lower if c.isalpha()]
        if letters and sum(1 for c in letters if ord(c) > 127) / len(letters) > self.non_ascii_ratio:
            return "non_english_script"
        for name, on, rx in self.rules:
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
