#!/usr/bin/env python3
"""Read the evidence columns of keyword exports: which tool wrote the file, market and date from the file name, tool
intent, SERP features, trend series and Keyword Planner buckets. Pure functions (no file access). Standard library only.

Formats were checked on real export files (references/export-formats.md, level D); vendor documentation was read
through search summaries only, so every mapping below is a [Convention] of the vendor, not a Google fact.
"""
from __future__ import annotations

import re
import unicodedata

NA = {"", "-", "--", "n/a", "na", "null", "none", "nan", "—"}
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
MONTH_COL_RX = re.compile(r"^searches:\s*([a-z]{3})[a-z]*\s+(\d{4})$")  # Keyword Planner 'Searches: May 2025'
TREND_RANGE_RX = re.compile(r"\((\d{1,2})-(\d{4})\s*-\s*(\d{1,2})-(\d{4})\)")  # Ahrefs 'SV trend (09-2024 - 08-2026)'


def _h(header: str) -> str:
    h = unicodedata.normalize("NFC", header or "").replace("﻿", "").replace(" ", " ").strip().strip('"').lower()
    return re.sub(r"\s+", " ", h)


def _hset(headers) -> set[str]:
    out = set()
    for h in headers:
        base = _h(h)
        out |= {base, re.sub(r"\s*\(.*?\)\s*$", "", base)}
    return out


# --------------------------------------------------------------------------- which tool wrote the file
BOOL_INTENT_COLUMNS = {"branded", "local", "informational", "commercial", "transactional", "navigational"}


def detect_source_tool(headers, filename: str = "") -> str:
    """Name the tool from the header (and the file name for Semrush Keyword Magic Tool). First match wins; the header
    names come from real exports (references/export-formats.md). 'generic' = a hand-made sheet or an unknown tool."""
    h, name = _hset(headers), (filename or "").lower()
    if "main keyword" in h and ({"thuộc pillar", "category kind"} & h):
        return "team-plan"
    if ("page" in h and "topic" in h) or "page type" in h or "seed keyword" in h:
        return "semrush-ksb"
    if "current url" in h and BOOL_INTENT_COLUMNS & h:
        return "ahrefs-se"
    if "position" in h and "url" in h:
        return "semrush-positions"
    if "keyword difficulty index" in h or "database" in h:
        return "semrush-api"
    if {"parent keyword", "parent topic", "traffic potential"} & h:
        return "ahrefs-ke"
    if "avg. monthly searches" in h:
        return "gkp"
    if "top queries" in h or {"impressions", "ctr"} <= h:
        return "gsc"
    if ({"competitive density", "number of results"} & h or ("trend" in h and "keyword difficulty" in h)
            or re.search(r"_(broad-match|phrase-match|exact-match|related|all-keywords|questions)_", name)):
        return "semrush-kmt"
    return "generic"


def vendor(tool: str) -> str:
    """'semrush-kmt' -> 'semrush'; the vendor name used in short labels."""
    return {"gkp": "keyword planner", "gsc": "search console", "team-plan": "team plan"}.get(tool, tool.split("-")[0])


# --------------------------------------------------------------------------- market and date from the file name
FILENAME_PATTERNS = [  # (label, regex with groups db?, yyyy, mm, dd)
    ("-organic.Positions-<db>-YYYYMMDD", re.compile(r"-organic\.positions-([a-z]{2})-(\d{4})(\d{2})(\d{2})")),
    ("google_<db>_", re.compile(r"^google_([a-z]{2})_(?:.*?_(\d{4})-(\d{2})-(\d{2}))?")),
    ("_(clusters|list)_YYYY-MM-DD", re.compile(r"_(?:clusters|list)_()(\d{4})-(\d{2})-(\d{2})")),
    ("_<db>_YYYY-MM-DD", re.compile(r"_([a-z]{2})_(\d{4})-(\d{2})-(\d{2})")),
]
MARKET_CODES = {"gb": "uk"}  # Ahrefs writes the UK database as 'gb', Semrush as 'uk'


def market_date_from_filename(name: str) -> tuple[str, str, str]:
    """(market, 'YYYY-MM-DD' or '', pattern label) from the names Semrush and Ahrefs give their exports, e.g.
    'gifts_broad-match_us_2026-05-01.csv', 'site.com-organic.Positions-uk-20260628.csv', 'google_gb_gifts_...csv'.
    ('', '', '') when no pattern matches. The caller uses the market only when the file has no market column and no
    ::market suffix, and says so in the report."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    for label, rx in FILENAME_PATTERNS:
        m = rx.search(base)
        if m:
            db, y, mo, d = m.groups()
            return MARKET_CODES.get(db, db or ""), (f"{y}-{mo}-{d}" if y else ""), label
    return "", "", ""


# --------------------------------------------------------------------------- tool intent
INTENT_WORDS = ("informational", "commercial", "transactional", "navigational")
INTENT_LETTERS = {"i": "informational", "n": "navigational", "c": "commercial", "t": "transactional"}
INTENT_CODES = {"0": "commercial", "1": "informational", "2": "navigational", "3": "transactional"}  # Semrush API


def _bool(raw) -> bool | None:
    s = str(raw or "").strip().lower()
    return True if s in ("true", "1", "yes", "y") else False if s in ("false", "0", "no", "n") else None


def parse_intent(raw, flags: dict | None = None) -> tuple[frozenset, bool | None, bool | None]:
    """(labels, branded, local). Reads Semrush words in any case ('Commercial, Informational'), Semrush API codes
    ('1,0': 0=commercial, 1=informational, 2=navigational, 3=transactional), the I/N/C/T badges copied from the UI,
    Ahrefs 'Branded/Non-branded/Local/Non-local', and Ahrefs Site Explorer true/false columns passed in `flags`
    ({'informational': 'true', 'branded': 'false', ...}). A label is the tool's hint, not proof [Convention]."""
    labels, branded, local = set(), None, None
    s = str(raw or "").strip().lower()
    compact = re.sub(r"\s+", "", s)
    if re.fullmatch(r"[0-3](,[0-3])*", compact):
        labels = {INTENT_CODES[c] for c in compact.split(",")}
    elif s not in NA:
        for tok in re.split(r"[,;|/\s]+", re.sub(r"\bnon[\s_-]*", "non-", s)):
            if tok in INTENT_WORDS:
                labels.add(tok)
            elif tok in INTENT_LETTERS:
                labels.add(INTENT_LETTERS[tok])
            elif tok in ("branded", "non-branded"):
                branded = tok == "branded"
            elif tok in ("local", "non-local"):
                local = tok == "local"
    for name, val in (flags or {}).items():
        b = _bool(val)
        if b is None:
            continue
        if name == "branded":
            branded = b
        elif name == "local":
            local = b
        elif name in INTENT_WORDS and b:
            labels.add(name)
    return frozenset(labels), branded, local


# --------------------------------------------------------------------------- SERP features
SERP_FEATURE_SLUGS = {
    "featured snippet": "featured_snippet", "featured snippets": "featured_snippet",
    "people also ask": "paa",
    "ai overview": "ai_overview", "ai overviews": "ai_overview",
    "image pack": "image_pack", "images": "image_pack", "image": "image_pack", "featured images": "image_pack",
    "video": "video", "videos": "video", "video carousel": "video", "video preview": "video",
    "short videos": "video", "featured video": "video",
    "popular products": "shopping", "shopping ads": "shopping", "shopping": "shopping", "shopping results": "shopping",
    "local pack": "local_pack", "local results": "local_pack",
    "top stories": "top_stories",
    "knowledge panel": "knowledge_panel", "knowledge graph": "knowledge_panel", "knowledge card": "knowledge_panel",
    "discussions and forums": "discussions", "discussions": "discussions",
    "ads top": "ads", "ads bottom": "ads", "adwords top": "ads", "adwords bottom": "ads", "top ads": "ads",
    "bottom ads": "ads", "ads": "ads", "paid": "ads",
    "sitelinks": "sitelinks", "site links": "sitelinks",
    "things to know": "things_to_know",
    "reviews": "reviews",
    "instant answer": "instant_answer",
    "thumbnail": "thumbnail", "thumbnails": "thumbnail",
}
INFO_FEATURES = frozenset({"paa", "featured_snippet", "ai_overview"})  # an informational SERP [Convention mapping]


def parse_serp_features(raw) -> frozenset:
    """Slugs from the names each tool and version uses: KMT 'People also ask, AI Overview', KSB 'Site Links', Organic
    Research codes 'people_also_ask,ai_overview', Ahrefs 'Top stories,Thumbnail'. Unknown names are kept as
    'other:<name>' (including Semrush API number codes, whose mapping was not verified); 'organic' is not a feature."""
    out = set()
    for part in re.split(r"[,;|\n]", str(raw or "").lower().replace("_", " ")):
        name = re.sub(r"\s+", " ", part).strip().strip('"').strip()
        if name in NA or name == "organic":
            continue
        out.add(SERP_FEATURE_SLUGS.get(name) or f"other:{name}")
    return frozenset(out)


# --------------------------------------------------------------------------- trend and monthly searches
def ym_add(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7]) - 1 + n
    return f"{y + m // 12:04d}-{m % 12 + 1:02d}"


def month_name(ym: str) -> str:
    return MONTHS[int(ym[5:7]) - 1].capitalize() if ym else ""


def monthly_columns(headers) -> list[tuple[int, str]]:
    """Keyword Planner 'Searches: May 2025' columns -> [(column index, '2025-05')], in file order."""
    out = []
    for i, h in enumerate(headers):
        m = MONTH_COL_RX.match(_h(h))
        if m and m.group(1) in MONTHS:
            out.append((i, f"{m.group(2)}-{MONTHS.index(m.group(1)) + 1:02d}"))
    return out


def trend_header_range(header: str) -> tuple[str, str] | None:
    """Ahrefs 'SV trend (09-2024 - 08-2026)' -> ('2024-09', '2026-08'); None when the header names no months."""
    m = TREND_RANGE_RX.search(header or "")
    if not m:
        return None
    return f"{m.group(2)}-{int(m.group(1)):02d}", f"{m.group(4)}-{int(m.group(3)):02d}"


def parse_trend(raw, header: str = "") -> tuple[tuple, str]:
    """(values, scale). Semrush 'Trend' '0.20,1.00,0.82,...' (relative, peak month = 1.00, oldest to newest),
    Organic Research 'Trends' '[100,82,...]' (relative 0-100, divided by 100) and Ahrefs 'SV trend (MM-YYYY -
    MM-YYYY)' '2181, 1845, ...' (absolute monthly volumes; the months are in the header, see trend_header_range).
    ((), '') when the cell is empty or in an unknown form."""
    s = str(raw or "").strip()
    if s.lower() in NA:
        return (), ""
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]
    if not nums:
        return (), ""
    if _h(header).startswith("sv trend"):
        return tuple(nums), "absolute"
    if s.startswith("["):
        return tuple(round(v / 100, 4) for v in nums), "relative"
    if max(nums) <= 1.0:
        return tuple(nums), "relative"
    return (), ""


def peak_month(values, end: str) -> str:
    """Month name of the highest value when the series is anchored (end = 'YYYY-MM' of the last value), else ''.
    Ties go to the most recent month."""
    if not values or not end:
        return ""
    best = max(range(len(values)), key=lambda i: (values[i], i))
    return month_name(ym_add(end, best - (len(values) - 1)))


# --------------------------------------------------------------------------- Keyword Planner buckets
# Low-spend Google Ads accounts get ranges; real exports write them as 0/50/500/5000/50000... [Research: observed in
# real exports, references/export-formats.md]. Each value is mapped back to the range Keyword Planner shows.
KP_BUCKETS = {0: (0, 10, "0–10"), 50: (10, 100, "10–100"), 500: (100, 1000, "100–1K"), 5000: (1000, 10000, "1K–10K"),
              50000: (10000, 100000, "10K–100K"), 500000: (100000, 1000000, "100K–1M"),
              5000000: (1000000, 10000000, "1M–10M")}


def kp_bucket_range(v) -> str | None:
    """'1K–10K' for a Keyword Planner bucket value (5000), None for any other value."""
    if v is None or float(v) != int(v):
        return None
    b = KP_BUCKETS.get(int(v))
    return b[2] if b else None


def kp_bucket_value(v, range_mode: str = "low") -> float:
    """The bound of the bucket's range that --range-mode picks, so a bucket reads like the same range typed as text."""
    lo, hi, _ = KP_BUCKETS[int(v)]
    return {"low": lo, "high": hi, "mid": (lo + hi) / 2}.get(range_mode, lo)


def is_kp_bucketed(volumes, monthly_cells) -> bool:
    """A whole Keyword Planner file holds buckets when every non-empty volume is a bucket value and every monthly
    'Searches:' cell is empty (exact exports fill them). One exact-looking 50 with filled months stays exact."""
    vols = [v for v in volumes if v is not None]
    return bool(vols) and all(kp_bucket_range(v) for v in vols) and all(
        str(c or "").strip().lower() in NA for c in monthly_cells)


# --------------------------------------------------------------------------- Search Console Filters sheet
def gsc_filters(rows) -> dict:
    """Search Console's Filters.csv / Filters sheet ('Filter,Value' then 'Country,United States', 'Date,Last 3
    months', ...) -> {'country': 'United States', 'date': 'Last 3 months', ...}."""
    out = {}
    for cells in rows:
        if len(cells) >= 2 and _h(cells[0]) and _h(cells[0]) != "filter":
            out[_h(cells[0])] = str(cells[1]).strip()
    return out
