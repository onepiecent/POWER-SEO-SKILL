#!/usr/bin/env python3
"""Đọc file export keyword "thật" của SEO Specialist. Chỉ dùng thư viện chuẩn.

Xử lý các tình huống hay gặp:
  * UTF-16 + tab (Google Keyword Planner, một số bản export Ahrefs), UTF-8 có BOM, cp1252;
  * dòng tiêu đề không nằm ở dòng đầu (Keyword Planner có 2-3 dòng mô tả phía trên);
  * dấu phân cách , ; tab |;
  * số kiểu 1,234 / 1.234 / 1K / 1.2M / "1K - 10K" / "<10" / "35%";
  * tên cột của Semrush, Ahrefs, Keyword Planner, Google Search Console, Google Sheets tự tạo.
"""
from __future__ import annotations

import csv
import re
from typing import Iterator

DELIMS = [",", "\t", ";", "|"]
SCAN_LINES = 40
NA_VALUES = {"", "-", "--", "n/a", "na", "null", "none", "nan", "—"}

ALIASES = {
    "keyword": ["keyword", "keywords", "query", "queries", "top queries", "top query", "search term",
                "search terms", "term", "phrase"],
    "volume": ["volume", "search volume", "avg. monthly searches", "avg monthly searches", "monthly searches",
               "monthly volume", "sv", "us volume", "uk volume"],
    "impressions": ["impressions"],
    "clicks": ["clicks"],
    "kd": ["kd", "kd %", "kd%", "keyword difficulty", "difficulty", "seo difficulty"],
    "cpc": ["cpc", "cost per click"],
    "market": ["market", "country", "location", "geo", "country code"],
    "serp": ["serp_urls", "serp urls", "top_urls", "top urls", "serp", "top 10 urls", "serp results"],
    "intent": ["intent", "intents", "search intent"],
    "parent": ["parent topic", "parent_topic", "parent keyword"],
    "position": ["position", "avg. position", "average position", "current position"],
}
VOLUME_FALLBACK_ORDER = ["volume", "impressions", "clicks"]


def norm_header(h: str) -> str:
    h = (h or "").replace("\ufeff", "").replace("\u00a0", " ").strip().strip('"').lower()
    return re.sub(r"\s+", " ", h)


def header_variants(h: str) -> list[str]:
    base = norm_header(h)
    return [base, re.sub(r"\s*\(.*?\)\s*$", "", base)]  # "cpc (usd)" -> "cpc"


# --------------------------------------------------------------------------- decoding
def decode_bytes(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace"), "utf-8-sig"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace"), "utf-16"
    head = data[:4096]
    if head and head.count(b"\x00") > len(head) // 4:
        enc = "utf-16-le" if head[1:2] == b"\x00" else "utf-16-be"
        return data.decode(enc, errors="replace"), enc
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace"), "cp1252"


def split_line(line: str, delim: str) -> list[str]:
    try:
        return next(csv.reader([line], delimiter=delim))
    except (StopIteration, csv.Error):
        return [line]


# --------------------------------------------------------------------------- numbers
def parse_number(raw, integer: bool = False, range_mode: str = "low") -> tuple[float | None, bool]:
    """Trả (giá trị, là-ước-lượng). Ước lượng khi gặp khoảng ("1K - 10K") hoặc cận ("<10")."""
    if raw is None:
        return None, False
    s = str(raw).strip()
    if s.lower() in NA_VALUES:
        return None, False
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    m = re.match(r"^\s*([^\-]+?)\s*-\s*([^\-]+?)\s*$", s)
    if m and re.search(r"\d", m.group(1)) and re.search(r"\d", m.group(2)):
        lo, _ = parse_number(m.group(1), integer, range_mode)
        hi, _ = parse_number(m.group(2), integer, range_mode)
        if lo is not None and hi is not None:
            return {"low": lo, "high": hi, "mid": (lo + hi) / 2}.get(range_mode, lo), True
    estimated = s[:1] in "<>~\u2248\u2264\u2265"
    t = re.sub(r"[\s\u00a0\u202f]", "", s.lstrip("<>~\u2248\u2264\u2265$\u00a3\u20ac")).rstrip("%")
    mult = 1
    if t and t[-1] in "kKmM":
        mult = 1000 if t[-1] in "kK" else 1_000_000
        t = t[:-1]
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", t) else t.replace(",", ".")
    elif "." in t and integer and re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    try:
        return float(t) * mult, estimated
    except ValueError:
        return None, False


MARKET_MAP = {
    "us": "us", "usa": "us", "united states": "us", "united states of america": "us", "en-us": "us", "2840": "us",
    "uk": "uk", "gb": "uk", "gbr": "uk", "united kingdom": "uk", "great britain": "uk", "en-gb": "uk", "2826": "uk",
}


def norm_market(raw) -> str:
    s = (raw or "").strip().lower()
    return MARKET_MAP.get(s, s or "")


# --------------------------------------------------------------------------- reading
class Table:
    """Kết quả đọc một file: info (thông tin phát hiện được) và iterator các bản ghi chuẩn hóa tên cột."""

    def __init__(self, info: dict, rows: Iterator[dict]):
        self.info, self.rows = info, rows

    def __iter__(self):
        return self.rows


def _find_header(lines: list[str], keyword_names: set[str]) -> tuple[int, str]:
    for i, line in enumerate(lines[:SCAN_LINES]):
        best = None
        for delim in DELIMS:
            cells = split_line(line, delim)
            if any(v in keyword_names for c in cells for v in header_variants(c)):
                if best is None or len(cells) > best[0]:
                    best = (len(cells), delim)
        if best:
            return i, best[1]
    preview = "\n".join(lines[:5])
    raise SystemExit("Không tìm thấy dòng tiêu đề có cột keyword/query trong 40 dòng đầu.\n"
                     "Dùng --map keyword=<tên cột> nếu tên cột khác thường. 5 dòng đầu:\n" + preview)


def read_keywords(path: str, overrides: dict | None = None) -> Table:
    overrides = {k: norm_header(v) for k, v in (overrides or {}).items()}
    with open(path, "rb") as fh:
        text, encoding = decode_bytes(fh.read())
    lines = text.splitlines()
    keyword_names = set(ALIASES["keyword"]) | ({overrides["keyword"]} if "keyword" in overrides else set())
    header_idx, delim = _find_header(lines, keyword_names)
    header = split_line(lines[header_idx], delim)
    colmap: dict[str, int] = {}
    used_headers: dict[str, str] = {}
    for canon in ALIASES:
        candidates = ([overrides[canon]] if canon in overrides else []) + ALIASES[canon]
        for cand in candidates:
            for idx, h in enumerate(header):
                if cand in header_variants(h) and idx not in colmap.values():
                    colmap[canon] = idx
                    used_headers[canon] = h.strip()
                    break
            if canon in colmap:
                break
    volume_source = next((c for c in VOLUME_FALLBACK_ORDER if c in colmap), "none")
    info = {"path": path, "encoding": encoding, "delimiter": {"\t": "TAB"}.get(delim, delim),
            "header_row": header_idx + 1, "columns": used_headers, "volume_source": volume_source,
            "rows": 0, "skipped_blank": 0}

    def generate() -> Iterator[dict]:
        reader = csv.reader(lines[header_idx + 1:], delimiter=delim)
        for cells in reader:
            if not any(c.strip() for c in cells):
                info["skipped_blank"] += 1
                continue
            rec = {canon: (cells[idx].strip() if idx < len(cells) else "") for canon, idx in colmap.items()}
            info["rows"] += 1
            yield rec

    return Table(info, generate())
