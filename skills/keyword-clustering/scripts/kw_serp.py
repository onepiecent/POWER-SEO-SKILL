#!/usr/bin/env python3
"""SERP data checked by hand or exported (serp.csv, cluster_keywords.py --serp): the top-10 organic URLs of a keyword,
used to cluster by shared URLs. Standard library only.

Two layouts, CSV or .xlsx (the sheet 'SERP', else the first sheet):
  long   one row per result: keyword, url [, market, position, title, checked_at, source]
         (what printerval-blog-seo/assets/serp-extract.js copies from a Google results page)
  wide   one row per keyword: keyword, serp_urls (URLs separated by '|' or spaces) [, market, checked_at, source]
The rows of one keyword and market are joined in position order (positions above 10 are ignored). A keyword checked on
several dates keeps the latest check only. A row without a market applies to the keyword in every market (warning:
US and UK SERPs differ). URLs are normalised like the export's serp_urls column (no scheme, no www, no query string,
no trailing slash), so 'https://www.a.com/x/?utm=1' and 'a.com/x' are the same result.
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
import zipfile
from collections import defaultdict

from kw_decisions import decision_key
from kw_ingest import _xlsx_rows, _xlsx_sheets, _xlsx_shared_strings, decode_bytes, is_xlsx, norm_market

TOP = 10
HEADS = {"keyword": ("keyword", "query", "search_term", "keywords"), "url": ("url", "link", "result_url"),
         "serp_urls": ("serp_urls", "top_urls", "top_10_urls", "serp"), "market": ("market", "country", "database", "gl"),
         "position": ("position", "pos", "rank"), "title": ("title",), "checked_at": ("checked_at", "date", "checked"),
         "source": ("source", "method")}


def norm_url(u: str) -> str:
    u = re.sub(r"^https?://(www\.)?", "", (u or "").strip().lower())
    return re.split(r"[?#]", u)[0].rstrip("/")


def _head(cell) -> str:
    return re.sub(r"[\s\-]+", "_", unicodedata.normalize("NFC", str(cell or "")).replace("﻿", "").strip().lower())


def _rows(path: str) -> list[list[str]]:
    if is_xlsx(path):
        with zipfile.ZipFile(path) as zf:
            sheets = [(name, p) for name, p in _xlsx_sheets(zf) if p in zf.namelist()]
            if not sheets:
                raise SystemExit(f"--serp {path}: the workbook has no readable sheet")
            _, sheet = next((s for s in sheets if s[0].strip().lower() == "serp"), sheets[0])
            return list(_xlsx_rows(zf, sheet, _xlsx_shared_strings(zf)))
    with open(path, "rb") as fh:
        text, _ = decode_bytes(fh.read())
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    return list(csv.reader(io.StringIO(text, newline=""), delimiter=max(",;\t", key=first.count)))


class SerpEntry:
    __slots__ = ("market", "keyword", "urls", "titles", "checked_at", "source")

    def __init__(self, market: str, keyword: str, checked_at: str, source: str):
        self.market, self.keyword, self.checked_at, self.source = market, keyword, checked_at, source
        self.urls: list[str] = []
        self.titles: list[str] = []


def _position(raw: str, default: int) -> int:
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default


def read_serp(paths: list[str]) -> tuple[dict[tuple, SerpEntry], list[str]]:
    """{(market, decision key): SerpEntry} from every file (a later file wins for the same keyword and date), and the
    warnings."""
    out: dict[tuple, SerpEntry] = {}
    warnings: list[str] = []
    for path in paths:
        rows = _rows(path)
        for n, cells in enumerate(rows[:10]):
            heads = [_head(c) for c in cells]
            col = {}
            for field, names in HEADS.items():
                i = next((heads.index(h) for h in names if h in heads), None)
                if i is not None:
                    col[field] = i
            if "keyword" in col and ("url" in col or "serp_urls" in col):
                break
        else:
            raise SystemExit(f"--serp {path}: no header row with keyword and url (one row per result) or keyword and "
                             "serp_urls (one row per keyword) in the first 10 rows")

        def cell(cells: list[str], field: str) -> str:
            i = col.get(field)
            return str(cells[i]).strip() if i is not None and i < len(cells) else ""
        got: dict[tuple, list] = defaultdict(list)
        meta: dict[tuple, tuple] = {}
        no_market = 0
        for m, cells in enumerate(rows[n + 1:]):
            kw = cell(cells, "keyword")
            if not kw:
                continue
            market = norm_market(cell(cells, "market")) if cell(cells, "market") else ""
            no_market += not market
            key = (market, decision_key(kw), cell(cells, "checked_at"))
            meta.setdefault(key, (kw, cell(cells, "source")))
            if "url" in col:
                u, pos = norm_url(cell(cells, "url")), _position(cell(cells, "position"), 1000 + m)
                if u and (pos <= TOP or pos >= 1000):  # a position above 10 is not on page one; none: file order
                    got[key].append((pos, u, cell(cells, "title")))
            else:
                for i, u in enumerate(x for x in re.split(r"[|\s]+", cell(cells, "serp_urls")) if x.strip()):
                    got[key].append((i + 1, norm_url(u), ""))
        if no_market:
            warnings.append(f"--serp {path}: {no_market} row(s) without a market apply to the keyword in every market "
                            "(US and UK SERPs differ: add a market column)")
        for (market, k, date), results in sorted(got.items(), key=lambda kv: kv[0][2]):  # the latest date wins
            e = SerpEntry(market, meta[(market, k, date)][0], date, meta[(market, k, date)][1])
            for _, u, title in sorted(results):
                if u not in e.urls and len(e.urls) < TOP:
                    e.urls.append(u)
                    e.titles.append(title)
            if e.urls:
                out[(market, k)] = e
    return out, warnings


def lookup(serp: dict[tuple, SerpEntry], market: str, text: str) -> SerpEntry | None:
    key = decision_key(text)
    return serp.get((market, key)) or serp.get(("", key))


def apply_serp(rows: list, serp: dict[tuple, SerpEntry]) -> tuple[int, int]:
    """Set k.urls from the SERP file for every keyword (or one of its variants) it has: the file wins over an
    export's serp_urls column (it is the newer check). Returns (keywords matched, SERP entries no keyword matched)."""
    used, matched = set(), 0
    for k in rows:
        for text in (k.keyword, *k.variants):
            e = lookup(serp, k.market, text)
            if e is not None:
                k.urls = frozenset(e.urls)
                used.add(id(e))
                matched += 1
                break
    return matched, sum(1 for e in serp.values() if id(e) not in used)
