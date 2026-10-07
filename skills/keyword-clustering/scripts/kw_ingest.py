#!/usr/bin/env python3
"""Read "real" keyword export files from SEO specialists. Standard library only.

Situations handled:
  * Excel workbooks (.xlsx/.xlsm, the default Semrush export): read_tables reads every sheet with a keyword column
    (one per group in a Semrush "export with groups" or a hand-made workbook); read_keywords reads the first one;
  * UTF-16 + tab (Google Keyword Planner, some Ahrefs exports), UTF-8 with BOM, cp1252;
  * the header row is not the first line (Keyword Planner has 2-3 description lines above it);
  * delimiters , ; tab |; a quoted cell may hold several lines (Alt+Enter in Sheets/Excel) and stays one cell;
  * numbers such as 1,234 / 1.234 / 1K / 1.2M / "1K - 10K" / "<10" / "35%";
  * column names from Semrush, Ahrefs, Keyword Planner, Google Search Console, hand-made Google Sheets and
    Vietnamese headers (NFC-normalised); every column that is not used is listed in info["ignored_columns"].
"""
from __future__ import annotations

import csv
import io
import os
import posixpath
import re
import unicodedata
import zipfile
from typing import Iterator
from xml.etree import ElementTree as ET

from kw_evidence import detect_source_tool, gsc_filters, market_date_from_filename, monthly_columns

DELIMS = [",", "\t", ";", "|"]
SCAN_LINES = 40
NA_VALUES = {"", "-", "--", "n/a", "na", "null", "none", "nan", "—"}

ALIASES = {
    "keyword": ["keyword", "keywords", "query", "queries", "top queries", "top query", "search term",
                "search terms", "term", "phrase", "từ khóa", "từ khoá"],
    "volume": ["volume", "search volume", "avg. monthly searches", "avg monthly searches", "monthly searches",
               "monthly volume", "sv", "us volume", "uk volume"],
    "impressions": ["impressions"],
    "clicks": ["clicks"],
    # Semrush Personal Keyword Difficulty is preferred when both are exported
    "kd": ["personal keyword difficulty", "kd", "kd %", "kd%", "keyword difficulty", "keyword difficulty index",
           "difficulty", "seo difficulty"],
    "cpc": ["cpc", "cost per click"],
    "market": ["market", "country", "location", "geo", "country code", "database"],
    "serp": ["serp_urls", "serp urls", "top_urls", "top urls", "serp", "top 10 urls", "serp results"],
    "intent": ["intent", "intents", "search intent", "keyword intents"],
    "parent": ["parent topic", "parent_topic", "parent keyword"],
    "position": ["position", "avg. position", "average position", "current position"],
    # evidence columns (kw_evidence.py reads their values)
    "serp_features": ["serp features", "serp features by keyword"],
    "trend": ["trend", "trends", "sv trend"],  # the raw header is kept: Ahrefs puts the month range in brackets
    "traffic_potential": ["traffic potential"],
    "ranking_url": ["url", "current url"],
    "competitive_density": ["competitive density"],
    "results": ["number of results"],
    "click_potential": ["click potential"],
    "change_3m": ["three month change"],
    "change_yoy": ["yoy change"],
    "flag_branded": ["branded"],  # Ahrefs Site Explorer true/false columns
    "flag_local": ["local"],
    "flag_informational": ["informational"],
    "flag_commercial": ["commercial"],
    "flag_transactional": ["transactional"],
    "flag_navigational": ["navigational"],
    # columns of a file that was already grouped ('topic' is handled in _colmap: a pillar beside 'page', else a group)
    "group": ["cluster", "cluster name", "group", "keyword group", "nhóm", "cụm", "nhóm từ khóa", "nhóm từ khoá",
              "chủ đề"],
    "main": ["main keyword", "primary keyword", "từ khóa chính", "từ khoá chính", "page"],
    "secondary": ["secondary keyword", "secondary keywords", "từ khóa phụ", "từ khoá phụ"],
    "role": ["page type", "category kind"],
    "pillar": ["pillar", "thuộc pillar"],
    "stt": ["stt"],
    "status": ["trạng thái", "status"],
    "url_blog": ["url blog", "target url"],
    "category": ["category", "danh mục"],
}
VOLUME_FALLBACK_ORDER = ["volume", "impressions", "clicks"]
# Columns that look useful but must never feed a decision (shown as 'ignored on purpose' in the report).
IGNORED_ON_PURPOSE = {
    "global volume": "worldwide volume, not the US/UK market: never used as volume",
    "global traffic potential": "worldwide, not the US/UK market",
    "competition": "advertising competition, not SEO difficulty",
    "sv forecasting trend": "a forecast, not measured searches",
    "#": "row number",
}


def norm_header(h: str) -> str:
    h = unicodedata.normalize("NFC", h or "").replace("\ufeff", "").replace("\u00a0", " ").strip().strip('"').lower()
    return re.sub(r"\s+", " ", h)


ALIASES = {k: [norm_header(a) for a in v] for k, v in ALIASES.items()}  # NFC, like the headers they are matched to


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
    """Return (value, is_estimate). A value is an estimate for ranges ("1K - 10K") or bounds ("<10")."""
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


# --------------------------------------------------------------------------- xlsx (zip + XML, no third-party library)
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def is_xlsx(path: str) -> bool:
    if path.lower().endswith((".xlsx", ".xlsm")):
        return True
    try:
        with open(path, "rb") as fh:
            if fh.read(4) != b"PK\x03\x04":
                return False
        with zipfile.ZipFile(path) as zf:
            return "xl/workbook.xml" in zf.namelist()
    except (OSError, zipfile.BadZipFile):
        return False


def _col_index(ref: str) -> int:
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def _xlsx_sheets(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    """(sheet name, path of the sheet XML inside the zip), in workbook order."""
    rels = {}
    if "xl/_rels/workbook.xml.rels" in zf.namelist():
        for rel in ET.fromstring(zf.read("xl/_rels/workbook.xml.rels")):
            target = rel.get("Target", "")
            rels[rel.get("Id")] = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
    sheets = []
    for el in ET.fromstring(zf.read("xl/workbook.xml")).iter():
        if _local(el.tag) != "sheet":
            continue
        rid = next((v for k, v in el.attrib.items() if _local(k) == "id"), None)
        path = rels.get(rid) or f"xl/worksheets/sheet{len(sheets) + 1}.xml"
        sheets.append((el.get("name") or f"Sheet{len(sheets) + 1}", path))
    return sheets


def _xlsx_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    out = []
    for si in ET.fromstring(zf.read("xl/sharedStrings.xml")):
        if _local(si.tag) != "si":
            continue
        parts = []
        for child in si:  # plain <t>, or rich-text runs <r><t>; phonetic hints <rPh> are skipped
            name = _local(child.tag)
            if name == "t":
                parts.append(child.text or "")
            elif name == "r":
                parts += [t.text or "" for t in child if _local(t.tag) == "t"]
        out.append("".join(parts))
    return out


def _xlsx_rows(zf: zipfile.ZipFile, sheet_path: str, shared: list[str]) -> Iterator[list[str]]:
    with zf.open(sheet_path) as fh:
        for _, el in ET.iterparse(fh, events=("end",)):
            if _local(el.tag) != "row":
                continue
            cells: dict[int, str] = {}
            nxt = 0
            for c in el:
                if _local(c.tag) != "c":
                    continue
                idx = _col_index(c.get("r")) if c.get("r") else nxt
                nxt = idx + 1
                kind = c.get("t", "n")
                if kind == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter() if _local(x.tag) == "t")
                else:
                    v = next((x for x in c if _local(x.tag) == "v"), None)
                    raw = v.text if v is not None and v.text is not None else ""
                    if kind == "s":
                        val = shared[int(raw)] if raw.isdigit() and int(raw) < len(shared) else ""
                    elif kind == "b":
                        val = "TRUE" if raw == "1" else "FALSE"
                    else:
                        val = raw
                cells[idx] = val
            el.clear()
            yield [cells.get(i, "") for i in range(max(cells) + 1)] if cells else []


def _has_keyword_header(cells: list[str], keyword_names: set[str]) -> bool:
    return any(v in keyword_names for c in cells for v in header_variants(c))


def _no_keyword_sheet(preview: list[str]) -> SystemExit:
    return SystemExit("No sheet has a header row with a keyword/query column in its first 40 rows.\n"
                      "Use --map keyword=<column name> if the column has an unusual name. First rows:\n" + "\n".join(preview))


def _read_xlsx(path: str, keyword_names: set[str]) -> tuple[str, int, list[list[str]]]:
    """Return (sheet name, header row index, rows) for the first sheet that has a keyword column near the top."""
    with zipfile.ZipFile(path) as zf:
        shared = _xlsx_shared_strings(zf)
        preview = []
        for name, sheet_path in _xlsx_sheets(zf):
            if sheet_path not in zf.namelist():
                continue
            rows = list(_xlsx_rows(zf, sheet_path, shared))
            for i, cells in enumerate(rows[:SCAN_LINES]):
                if _has_keyword_header(cells, keyword_names):
                    return name, i, rows
            preview = preview or [f"[{name}] " + " | ".join(r) for r in rows[:5]]
    raise _no_keyword_sheet(preview)


def _read_xlsx_all(path: str, keyword_names: set[str]) -> tuple[list[tuple[str, int, list[list[str]]]], list[tuple]]:
    """Every sheet with a keyword column near the top: ([(sheet name, header row index, rows)], [(skipped sheet,
    reason, rows)]). A workbook with one sheet per group ('export with groups', hand-made files) loses nothing."""
    found, skipped, preview = [], [], []
    with zipfile.ZipFile(path) as zf:
        shared = _xlsx_shared_strings(zf)
        for name, sheet_path in _xlsx_sheets(zf):
            if sheet_path not in zf.namelist():
                skipped.append((name, "sheet XML missing", []))
                continue
            rows = list(_xlsx_rows(zf, sheet_path, shared))
            idx = next((i for i, cells in enumerate(rows[:SCAN_LINES]) if _has_keyword_header(cells, keyword_names)), None)
            if idx is not None:
                found.append((name, idx, rows))
                continue
            skipped.append((name, "no keyword column in the first 40 rows" if any(any(c.strip() for c in r) for r in rows)
                            else "empty", rows))
            preview = preview or [f"[{name}] " + " | ".join(r) for r in rows[:5]]
    if not found:
        raise _no_keyword_sheet(preview)
    return found, skipped


# --------------------------------------------------------------------------- reading
class Table:
    """Result of reading one file: info (what was detected) and an iterator of records with normalised column names."""

    def __init__(self, info: dict, rows: Iterator[dict]):
        self.info, self.rows = info, rows

    def __iter__(self):
        return self.rows


def _find_header(lines: list[str], keyword_names: set[str]) -> tuple[int, str]:
    for i, line in enumerate(lines[:SCAN_LINES]):
        best = None
        for delim in DELIMS:
            cells = split_line(line, delim)
            if _has_keyword_header(cells, keyword_names):
                if best is None or len(cells) > best[0]:
                    best = (len(cells), delim)
        if best:
            return i, best[1]
    preview = "\n".join(lines[:5])
    raise SystemExit("No header row with a keyword/query column found in the first 40 lines.\n"
                     "Use --map keyword=<column name> if the column has an unusual name. First 5 lines:\n" + preview)


def _colmap(header: list[str], overrides: dict) -> tuple[dict[str, int], dict[str, str]]:
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
    # 'Topic' is the pillar in a Semrush Keyword Strategy Builder export (beside 'Page', the post), else a group name
    names = [norm_header(h) for h in header]
    if "topic" in names and names.index("topic") not in colmap.values():
        canon = "pillar" if "page" in names else "group"
        if canon not in colmap:
            colmap[canon] = names.index("topic")
            used_headers[canon] = header[colmap[canon]].strip()
    return colmap, used_headers


def _make_table(path: str, encoding: str, delim_label: str, header_idx: int, header: list[str], body,
                overrides: dict, sheet: str | None = None) -> Table:
    colmap, used_headers = _colmap(header, overrides)
    months = monthly_columns(header)
    month_idx = {i for i, _ in months}
    ignored = []
    for idx, h in enumerate(header):
        if idx in colmap.values() or idx in month_idx or not h.strip():
            continue
        why = next((IGNORED_ON_PURPOSE[v] for v in header_variants(h) if v in IGNORED_ON_PURPOSE), "")
        ignored.append((h.strip(), why))
    volume_source = next((c for c in VOLUME_FALLBACK_ORDER if c in colmap), "none")
    fn_market, fn_date, fn_pattern = market_date_from_filename(os.path.basename(path))
    info = {"path": path, "encoding": encoding, "delimiter": delim_label,
            "header_row": header_idx + 1, "columns": used_headers, "volume_source": volume_source,
            "rows": 0, "skipped_blank": 0, "sheet": sheet or "", "sheets_read": [sheet] if sheet else [],
            "sheets_skipped": [], "ignored_columns": ignored, "monthly_columns": months,
            "source_tool": detect_source_tool(header, os.path.basename(path)), "filename_market": fn_market,
            "filename_date": fn_date, "filename_pattern": fn_pattern, "gsc_filters": None}

    def generate() -> Iterator[dict]:
        try:
            for cells in body:
                if not any(c.strip() for c in cells):
                    info["skipped_blank"] += 1
                    continue
                rec = {canon: (cells[idx].strip() if idx < len(cells) else "") for canon, idx in colmap.items()}
                if months:
                    rec["_monthly"] = {ym: (cells[idx].strip() if idx < len(cells) else "") for idx, ym in months}
                if sheet is not None:
                    rec["_sheet"] = sheet
                info["rows"] += 1
                yield rec
        except csv.Error as exc:
            raise SystemExit(f"{os.path.basename(path)}: cannot parse the CSV after data row {info['rows']} ({exc}). "
                             "A quote that is never closed makes the rest of the file one cell; fix that cell.")

    return Table(info, generate())


def _read_csv(path: str, overrides: dict, keyword_names: set[str]) -> Table:
    with open(path, "rb") as fh:
        text, encoding = decode_bytes(fh.read())
    # the header is found on physical lines; the body is parsed as a whole so a quoted cell keeps its line breaks
    head = text[:500_000].splitlines(keepends=True)[:SCAN_LINES]
    lines = [(ln.splitlines() or [""])[0] for ln in head]
    header_idx, delim = _find_header(lines, keyword_names)
    offset = sum(len(ln) for ln in head[:header_idx + 1])
    header = split_line(lines[header_idx], delim)
    body = csv.reader(io.StringIO(text[offset:], newline=""), delimiter=delim)
    return _make_table(path, encoding, {"\t": "TAB"}.get(delim, delim), header_idx, header, body, overrides)


def _keyword_names(overrides: dict) -> set[str]:
    return set(ALIASES["keyword"]) | ({overrides["keyword"]} if "keyword" in overrides else set())


def read_keywords(path: str, overrides: dict | None = None) -> Table:
    """The first table of the file (an .xlsx: the first sheet with a keyword column). read_tables reads every sheet."""
    overrides = {k: norm_header(v) for k, v in (overrides or {}).items()}
    keyword_names = _keyword_names(overrides)
    if is_xlsx(path):
        sheet, header_idx, xrows = _read_xlsx(path, keyword_names)
        return _make_table(path, "xlsx", f"sheet '{sheet}'", header_idx, xrows[header_idx], iter(xrows[header_idx + 1:]),
                           overrides)
    return _read_csv(path, overrides, keyword_names)


def read_tables(path: str, overrides: dict | None = None, header_names: set[str] | None = None) -> list[Table]:
    """One Table per sheet with a keyword column (one for a CSV); each record of an .xlsx carries '_sheet'.
    info['sheets_read'] / info['sheets_skipped'] (name, reason) say what happened to every sheet. A Search Console
    export also gets info['gsc_filters'] from its Filters sheet or the Filters.csv next to it ({} when absent).
    header_names: more column names that also mark a header row (a grouped file whose sheet has 'Main Keyword' but
    no 'Keyword' column, kw_prior.py)."""
    overrides = {k: norm_header(v) for k, v in (overrides or {}).items()}
    keyword_names = _keyword_names(overrides) | set(header_names or ())
    filters_rows = None
    if is_xlsx(path):
        found, skipped = _read_xlsx_all(path, keyword_names)
        tables = [_make_table(path, "xlsx", f"sheet '{name}'", idx, rows[idx], iter(rows[idx + 1:]), overrides, sheet=name)
                  for name, idx, rows in found]
        for t in tables:
            t.info["sheets_read"] = [name for name, _, _ in found]
            t.info["sheets_skipped"] = [(name, why) for name, why, _ in skipped]
        filters_rows = next((rows for name, _, rows in skipped if norm_header(name) == "filters"), None)
    else:
        tables = [_read_csv(path, overrides, keyword_names)]
        if tables[0].info["source_tool"] == "gsc":  # Search Console zips hold Queries.csv next to Filters.csv
            folder = os.path.dirname(os.path.abspath(path))
            sibling = next((f for f in sorted(os.listdir(folder)) if f.lower() == "filters.csv"), None)
            if sibling:
                with open(os.path.join(folder, sibling), "rb") as fh:
                    ftext, _ = decode_bytes(fh.read())
                filters_rows = list(csv.reader(io.StringIO(ftext, newline="")))
    for t in tables:
        if t.info["source_tool"] == "gsc":
            t.info["gsc_filters"] = gsc_filters(filters_rows or [])
    return tables
