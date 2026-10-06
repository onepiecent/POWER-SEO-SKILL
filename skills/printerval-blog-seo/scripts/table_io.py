#!/usr/bin/env python3
"""Read a CSV or .xlsx table into a list of dicts (standard library only).

Used by export_plan.py for the content team's own files: the list of published blog posts (--published) and a
previous final plan (--previous). The header row is the first row (within the first 20) that contains one of the
wanted column names; for .xlsx the first sheet that has such a row is used (an Excel/Google Sheets file may hold
helper sheets). Shared strings, inline strings, formulas (their cached value) and gaps between cells are handled.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
import xml.etree.ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _col_index(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group():
        n = n * 26 + ord(ch) - 64
    return n - 1


def _xlsx_sheets(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = {}
    if "xl/_rels/workbook.xml.rels" in zf.namelist():
        for r in ET.fromstring(zf.read("xl/_rels/workbook.xml.rels")):
            rels[r.get("Id")] = r.get("Target", "")
    out = []
    for i, s in enumerate(wb.iter(NS + "sheet"), 1):
        target = rels.get(s.get(REL_NS + "id"), f"worksheets/sheet{i}.xml").lstrip("/")
        out.append((s.get("name", f"Sheet{i}"), target if target.startswith("xl/") else "xl/" + target))
    return out


def _shared(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    return ["".join(t.text or "" for t in si.iter(NS + "t")) for si in ET.fromstring(zf.read("xl/sharedStrings.xml"))]


def _rows(zf: zipfile.ZipFile, part: str, shared: list[str]):
    for row in ET.fromstring(zf.read(part)).iter(NS + "row"):
        cells = {}
        for c in row.iter(NS + "c"):
            t, v = c.get("t"), c.find(NS + "v")
            if t == "s" and v is not None:
                val = shared[int(v.text)]
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(NS + "t"))
            else:
                val = v.text if v is not None and v.text is not None else ""
            if c.get("r"):
                cells[_col_index(c.get("r"))] = val
            else:
                cells[len(cells)] = val
        yield [cells.get(i, "") for i in range(max(cells) + 1)] if cells else []


def _find_header(rows: list[list[str]], wanted: set[str]) -> int | None:
    for i, r in enumerate(rows[:20]):
        names = {str(x).strip().lower() for x in r}
        if names & wanted:
            return i
    return None


def _as_dicts(rows: list[list[str]], h: int) -> list[dict]:
    header = [str(x).strip() for x in rows[h]]
    out = []
    for r in rows[h + 1:]:
        if not any(str(x).strip() for x in r):
            continue
        out.append({header[i] if i < len(header) and header[i] else f"col{i + 1}": (r[i] if i < len(r) else "")
                    for i in range(max(len(header), len(r)))})
    return out


def read_table(path: str, wanted: set[str], sheet: str | None = None) -> list[dict]:
    """Rows of the first table whose header has one of the wanted (lowercase) column names."""
    wanted = {w.lower() for w in wanted}
    if path.lower().endswith((".xlsx", ".xlsm")):
        with zipfile.ZipFile(path) as zf:
            shared = _shared(zf)
            for name, part in _xlsx_sheets(zf):
                if sheet and name != sheet:
                    continue
                rows = list(_rows(zf, part, shared))
                h = _find_header(rows, wanted)
                if h is not None:
                    return _as_dicts(rows, h)
        raise SystemExit(f"{path}: no sheet has a header with one of: {', '.join(sorted(wanted))}")
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:5000]
    delim = max(",;\t|", key=sample.count)
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    h = _find_header(rows, wanted)
    if h is None:
        raise SystemExit(f"{path}: no header with one of: {', '.join(sorted(wanted))}")
    return _as_dicts(rows, h)


def column(row: dict, names: list[str]) -> str:
    """Value of the first column whose lowercase name is in names."""
    low = {k.strip().lower(): v for k, v in row.items()}
    for n in names:
        if n in low and str(low[n]).strip():
            return str(low[n]).strip()
    return ""
