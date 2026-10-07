#!/usr/bin/env python3
"""Read a keyword file that an SEO specialist already grouped (cluster_keywords.py --prior). Standard library only.

Layouts, detected per file (the first match wins):
  plan  the team's final plan: a Plan sheet (STT, Main Keyword, Secondary Keyword, Category Kind, Thuộc Pillar), one
        group per STT. When the workbook has its Keyword Map sheet (STT, Keyword, Role), that sheet gives every
        keyword of each STT; it is more complete than the Secondary Keyword column.
  wide  a main keyword column and a secondary keyword column whose cells hold several keywords (split on a new line,
        ';' or '|', or on ',' when none of those is present); one row is one group (id = STT if present, else main).
        A Volume/KD on the row is the main keyword's.
  long  a keyword column and a group column (cluster, group, topic...); a blank group cell continues the group
        above it (a block of rows under one group name, or cells merged in Excel). The main keyword is the row's
        main keyword column when there is one; otherwise cluster_keywords.py names the group after its biggest keyword.
"""
from __future__ import annotations

import os
import re
from typing import NamedTuple

from kw_ingest import ALIASES, norm_header, read_tables

PLAN_HEADERS = frozenset(norm_header(h) for h in (
    "STT", "Main Keyword", "Secondary Keyword", "Volume", "KD", "Category", "Category Kind", "Thuộc Pillar",
    "Title SEO", "Meta Description SEO", "Outline", "Internal Link (Anchor || URL)", "Related Post (Anchor || URL)",
    "URL Blog", "Trạng thái"))
MAIN_HEADERS = frozenset(ALIASES["main"]) - {"page"}  # a sheet with 'Main Keyword' and no 'Keyword' column is read too
OVERRIDES = {"role": "role"}  # the Keyword Map sheet of the team's plan names the keyword's role in a 'Role' column
LIST_RX = re.compile(r"[\n;|]")


class PriorTag(NamedTuple):
    """Where the SEO put a keyword. KW.prior holds one per grouped-file row of that keyword (first = the group used)."""
    group_key: tuple    # (source file, group id): unique across files
    group: str          # the SEO's group id/name as text (prior_group)
    main: str           # the SEO's main keyword of the group ('' = not named; the biggest keyword is used)
    group_role: str     # Category Kind / page type of the group (prior_role of the cluster)
    role: str           # the keyword's role in the group: main, secondary, or the file's own word (prior_role)
    pillar: str         # Thuộc Pillar / pillar column (prior_pillar)
    is_main: bool


def split_list(cell: str) -> list[str]:
    """Keywords of a list cell: split on new lines, ';' or '|'; on ',' only when none of those is present."""
    cell = (cell or "").replace("\r", "\n")
    parts = LIST_RX.split(cell) if LIST_RX.search(cell) else cell.split(",")
    return [p for p in (re.sub(r"\s+", " ", x).strip().lstrip("-•*").strip() for x in parts) if p]


def _headers(info: dict) -> set[str]:
    return {norm_header(h) for h in info["columns"].values()} | {norm_header(h) for h, _ in info["ignored_columns"]}


def _rec(keyword, tag_args: dict, rec: dict, row_no: int, layout: str, src: str, with_numbers: bool) -> dict:
    return {"keyword": re.sub(r"\s+", " ", keyword).strip(), "market": rec.get("market", ""),
            "prior_volume": rec.get("volume", "") if with_numbers else "",
            "prior_kd": rec.get("kd", "") if with_numbers else "", "layout": layout, "source_file": src,
            "row_no": row_no, **tag_args}


def _row_groups(table, layout: str, src: str, by_stt: dict | None) -> list[dict]:
    """plan and wide: one group per row; members = main + secondary cells (or the Keyword Map rows of the STT)."""
    out = []
    for n, rec in enumerate(table, 1):
        main = re.sub(r"\s+", " ", rec.get("main", "")).strip()
        if not main:
            continue
        stt = rec.get("stt", "").strip()
        gid = stt or main
        base = {"group_key": (src, gid), "group": gid, "main": main, "group_role": rec.get("role", "").strip(),
                "pillar": rec.get("pillar", "").strip(), "stt": stt}
        members = by_stt.get(stt) if by_stt is not None and stt else None
        if members:
            for m_no, mrec in members:
                kw = re.sub(r"\s+", " ", mrec.get("keyword", "")).strip()
                is_main = kw.lower() == main.lower()
                out.append(_rec(kw, {**base, "role": mrec.get("role", "").strip() or ("main" if is_main else "secondary"),
                                     "is_main": is_main}, {**mrec, "market": rec.get("market", "")}, m_no, layout,
                                src, True))
            if not any(r["is_main"] and r["group_key"] == base["group_key"] for r in out):
                out.append(_rec(main, {**base, "role": "main", "is_main": True}, rec, n, layout, src, True))
            continue
        out.append(_rec(main, {**base, "role": "main", "is_main": True}, rec, n, layout, src, True))
        for kw in split_list(rec.get("secondary", "")):
            if kw.lower() != main.lower():
                out.append(_rec(kw, {**base, "role": "secondary", "is_main": False}, rec, n, layout, src, False))
    return out


def _long_groups(table, src: str) -> list[dict]:
    out, group, main, pillar, role = [], "", "", "", ""
    for n, rec in enumerate(table, 1):
        if rec.get("group", "").strip():  # a new group; a blank cell continues the one above (forward fill)
            group = rec["group"].strip()
            main, pillar, role = rec.get("main", "").strip(), rec.get("pillar", "").strip(), rec.get("role", "").strip()
        kw = re.sub(r"\s+", " ", rec.get("keyword", "")).strip()
        if not kw or not group:
            continue
        main = main or rec.get("main", "").strip()
        is_main = bool(main) and kw.lower() == main.lower()
        out.append(_rec(kw, {"group_key": (src, group), "group": group, "main": main, "group_role": role,
                             "role": "main" if is_main else "", "pillar": pillar or rec.get("pillar", "").strip(),
                             "stt": rec.get("stt", "").strip(), "is_main": is_main}, rec, n, "long", src, True))
    return out


def read_prior(path: str) -> tuple[list[dict], dict]:
    """(records, info) of a grouped file. A record: keyword, market (the row's cell, '' when none), group_key, group,
    main, group_role, role, pillar, stt, is_main, prior_volume, prior_kd, layout, source_file, row_no.
    info: the first table's info (filename_market...) plus 'layout', 'groups', 'sheets'."""
    tables = read_tables(path, OVERRIDES, header_names=MAIN_HEADERS)
    src = os.path.basename(path)
    sheet = {norm_header(t.info["sheet"]): t for t in tables}
    plan = next((t for t in tables if norm_header(t.info["sheet"]) == "plan" and "main" in t.info["columns"]), None)
    plan = plan or next((t for t in tables if {"main", "stt"} <= set(t.info["columns"])
                         and len(_headers(t.info) & PLAN_HEADERS) >= 4 and "keyword" not in t.info["columns"]), None)
    wide = next((t for t in tables if {"main", "secondary"} <= set(t.info["columns"])), None)
    long = next((t for t in tables if {"keyword", "group"} <= set(t.info["columns"])), None)
    if plan is not None:
        kmap = sheet.get("keyword map")
        by_stt = None
        if kmap is not None and {"keyword", "stt"} <= set(kmap.info["columns"]):
            by_stt = {}
            for n, rec in enumerate(kmap, 1):
                if rec.get("stt", "").strip() and rec.get("keyword", "").strip():
                    by_stt.setdefault(rec["stt"].strip(), []).append((n, rec))
        layout, table = "plan", plan
        records = _row_groups(plan, "plan", src, by_stt)
        sheets = [plan.info["sheet"]] + ([kmap.info["sheet"]] if by_stt is not None else [])
    elif wide is not None:
        layout, table = "wide", wide
        records, sheets = _row_groups(wide, "wide", src, None), [wide.info["sheet"]]
    elif long is not None:
        layout, table = "long", long
        records, sheets = _long_groups(long, src), [long.info["sheet"]]
    else:
        found = "; ".join(f"[{t.info['sheet'] or src}] {', '.join(t.info['columns'].values())}" for t in tables)
        raise SystemExit(f"--prior {src}: no grouped layout found. Expected a keyword column with a group column "
                         "(long), a main keyword column with a secondary keyword column (wide), or the team's final "
                         f"plan (Plan sheet). Columns found: {found}")
    info = dict(table.info)
    info.update(layout=layout, groups=len({r["group_key"] for r in records}), keywords=len(records),
                sheets=[s for s in sheets if s])
    return records, info
