#!/usr/bin/env python3
"""Read a keyword file that an SEO specialist already grouped (cluster_keywords.py --prior). Standard library only.

Layouts, detected per sheet (every sheet of a workbook is read; a sheet with no grouped layout is reported):
  plan  the team's final plan: a Plan sheet (STT, Main Keyword, Secondary Keyword, Category Kind, Thuộc Pillar), one
        group per STT. When the workbook has its Keyword Map sheet (STT, Keyword, Role), that sheet adds every
        keyword of each STT to the Secondary Keyword column.
  wide  a main keyword column and a secondary keyword column whose cells hold several keywords (split on a new line,
        ';' or '|', or on ',' when none of those is present); one row is one group (id = STT if present, else main).
        A Volume/KD on the row is the main keyword's.
  block the same columns, one keyword per row: a row with a Main keyword starts a group and the rows below it with an
        empty Main cell and a Secondary keyword continue it (the usual hand-made sheet); the Volume/KD of such a row
        belong to its secondary keyword. A Kind / Category Kind column (Pillar, Cluster) without a Thuộc Pillar
        column puts each Cluster group under the last group above it that is a Pillar or has no Kind (the head of
        the block).
  long  a keyword column and a group column (cluster, group, topic...); a blank group cell continues the group
        above it (a block of rows under one group name, or cells merged in Excel). The main keyword is the row's
        main keyword column when there is one; otherwise cluster_keywords.py names the group after its biggest keyword.
Keywords on rows above the first group are not dropped: they are returned without a group (the engine clusters them).
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
MAIN_HEADERS = frozenset(ALIASES["main"])  # a sheet with 'Main Keyword' and no 'Keyword' column is read too
OVERRIDES = {"role": "role"}  # the Keyword Map sheet of the team's plan names the keyword's role in a 'Role' column
LIST_RX = re.compile(r"[\n;|]")
PILLAR_ROLES = ("pillar", "pillar-hub", "pillar hub", "hub")
# the other sheets of the final plan (export_plan.py): never groups, even when they have keyword-like columns
PLAN_OUTPUT_SHEETS = frozenset({"schedule", "qa", "seo audit", "link plan", "research next", "published match",
                                "changes", "review", "back-check", "decisions", "not planned"})


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


def _clean(text) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _row_groups(table, layout: str, src: str, by_stt: dict | None, free: list[dict]) -> list[dict]:
    """plan, wide and block: a row with a main keyword starts a group (main + its Secondary cell, or the Keyword Map
    rows of its STT); a row without one continues the group above. Keywords before the first group go to free."""
    out: list[dict] = []
    sheet = table.info.get("sheet", "")
    cols = set(table.info["columns"])
    by_order = "role" in cols and "pillar" not in cols  # Kind column, no Thuộc Pillar: the Pillar above is the pillar
    cur, pillar_now, seen_gid = None, "", {}
    for n, rec in enumerate(table, 1):
        main = _clean(rec.get("main", ""))
        if not main:
            extra = split_list(rec.get("secondary", "")) or ([_clean(rec["keyword"])] if _clean(rec.get("keyword", "")) else [])
            one = len(extra) == 1  # the row's Volume/KD belong to its one keyword
            for kw in extra:
                if cur is None:
                    free.append(_rec(kw, {"group_key": None, "group": "", "main": "", "group_role": "", "role": "",
                                          "pillar": "", "stt": "", "is_main": False, "sheet": sheet}, rec, n, layout,
                                     src, one))
                elif kw.lower() != cur["main"].lower() or (rec.get("market") or "") != cur["_market"]:
                    # the main's text on a row of another market ('christmas gifts for dad' for the UK) is kept
                    out.append(_rec(kw, {**cur, "role": "secondary", "is_main": False}, rec, n, "block", src, one))
            continue
        stt = rec.get("stt", "").strip()
        gid = stt or main
        if seen_gid.get(gid, main.lower()) != main.lower():  # one STT used twice in a sheet: two groups
            gid = f"{gid} {main}"
        seen_gid[gid] = main.lower()
        role = rec.get("role", "").strip()
        pillar = rec.get("pillar", "").strip()
        if by_order:  # a Pillar row, or a row with no Kind that heads a block of Cluster rows, is the pillar below
            if role.lower() in PILLAR_ROLES or not role:
                pillar_now, pillar = main, ""
            else:
                pillar = pillar_now
        cur = {"group_key": (src, sheet, gid), "group": gid, "main": main, "group_role": role, "pillar": pillar,
               "stt": stt, "sheet": sheet, "_market": rec.get("market") or ""}
        members = by_stt.get(stt) if by_stt is not None and stt else None
        listed = {main.lower()}
        if members:
            for m_no, mrec in members:
                kw = _clean(mrec.get("keyword", ""))
                if not kw or kw.lower() in listed and kw.lower() != main.lower():
                    continue
                is_main = kw.lower() == main.lower()
                listed.add(kw.lower())
                out.append(_rec(kw, {**cur, "role": mrec.get("role", "").strip() or ("main" if is_main else "secondary"),
                                     "is_main": is_main}, {**mrec, "market": rec.get("market", "")}, m_no, layout,
                                src, True))
            if not any(r["is_main"] and r["group_key"] == cur["group_key"] for r in out):
                out.append(_rec(main, {**cur, "role": "main", "is_main": True}, rec, n, layout, src, True))
        else:
            out.append(_rec(main, {**cur, "role": "main", "is_main": True}, rec, n, layout, src, True))
        for kw in split_list(rec.get("secondary", "")):  # the Plan's own Secondary cell, also with a Keyword Map
            if kw.lower() not in listed:
                listed.add(kw.lower())
                out.append(_rec(kw, {**cur, "role": "secondary", "is_main": False}, rec, n, layout, src, False))
    return out


def _long_groups(table, src: str, free: list[dict]) -> list[dict]:
    out, group, main, pillar, role = [], "", "", "", ""
    sheet = table.info.get("sheet", "")
    for n, rec in enumerate(table, 1):
        if rec.get("group", "").strip():  # a new group; a blank cell continues the one above (forward fill)
            group = rec["group"].strip()
            main, pillar, role = rec.get("main", "").strip(), rec.get("pillar", "").strip(), rec.get("role", "").strip()
        kw = _clean(rec.get("keyword", ""))
        if not kw:
            continue
        if not group:
            free.append(_rec(kw, {"group_key": None, "group": "", "main": "", "group_role": "", "role": "", "pillar": "",
                                  "stt": "", "is_main": False, "sheet": sheet}, rec, n, "long", src, True))
            continue
        main = main or rec.get("main", "").strip()
        is_main = bool(main) and kw.lower() == main.lower()
        out.append(_rec(kw, {"group_key": (src, sheet, group), "group": group, "main": main, "group_role": role,
                             "role": "main" if is_main else "", "pillar": pillar or rec.get("pillar", "").strip(),
                             "stt": rec.get("stt", "").strip(), "is_main": is_main, "sheet": sheet}, rec, n, "long",
                        src, True))
    return out


def _layout(t) -> str:
    cols = set(t.info["columns"])
    if norm_header(t.info["sheet"]) == "plan" and "main" in cols:
        return "plan"
    if {"main", "stt"} <= cols and len(_headers(t.info) & PLAN_HEADERS) >= 4 and "keyword" not in cols:
        return "plan"
    if {"main", "secondary"} <= cols:
        return "wide"
    if {"keyword", "group"} <= cols:
        return "long"
    return ""


def read_prior(path: str) -> tuple[list[dict], dict]:
    """(records, info) of a grouped file. A record: keyword, market (the row's cell, '' when none), group_key, group,
    main, group_role, role, pillar, stt, sheet, is_main, prior_volume, prior_kd, layout, source_file, row_no. A record
    with group_key None is a keyword outside any group (rows above the first group): cluster it like an export row.
    info: the first grouped table's info (filename_market...) plus 'layout', 'groups', 'sheets', 'sheets_skipped'
    [(sheet, why)], 'free' (keywords outside any group) and 'block_rows' (rows that continued the group above)."""
    tables = read_tables(path, OVERRIDES, header_names=MAIN_HEADERS)
    src = os.path.basename(path)
    kmap = next((t for t in tables if norm_header(t.info["sheet"]) == "keyword map"
                 and {"keyword", "stt"} <= set(t.info["columns"])), None)
    kmap_sheet = kmap if kmap is not None and any(_layout(t) == "plan" for t in tables) else None
    records, free, layouts, sheets, first = [], [], [], [], None
    skipped = list(tables[0].info.get("sheets_skipped", [])) if tables else []
    from_plan = kmap_sheet is not None or any(norm_header(t.info["sheet"]) == "plan" for t in tables)
    for t in tables:
        if from_plan and norm_header(t.info["sheet"]) in PLAN_OUTPUT_SHEETS:
            skipped.append((t.info["sheet"], "a sheet of the final plan, not a grouping (Plan and Keyword Map are read)"))
            continue
        cols = t.info["columns"]
        if "group" not in cols and "keyword" in cols and norm_header(cols.get("ranking_url", "")) == "page":
            # Semrush Keyword Strategy Builder: Topic (the pillar) > Page (the post) > Keyword
            cols["group"] = cols.pop("ranking_url")
            t.rows = ({**{k: v for k, v in rec.items() if k != "ranking_url"}, "group": rec.get("ranking_url", "")}
                      for rec in t.rows)
        layout = _layout(t)
        if t is kmap_sheet:
            continue  # read with its Plan sheet
        if not layout:
            skipped.append((t.info["sheet"] or src, "no grouped layout (a keyword column with a group column, or a "
                            "main keyword column with secondary keywords): pass it as an export to cluster it"))
            continue
        by_stt = None
        if layout == "plan" and kmap is not None:
            by_stt = {}
            for n, rec in enumerate(kmap, 1):
                if rec.get("stt", "").strip() and rec.get("keyword", "").strip():
                    by_stt.setdefault(rec["stt"].strip(), []).append((n, rec))
        got = _long_groups(t, src, free) if layout == "long" else _row_groups(t, layout, src, by_stt, free)
        if any(r["layout"] == "block" for r in got):
            layout = "block"
        records += got
        layouts.append(layout)
        sheets.append(t.info["sheet"])
        if by_stt is not None:
            sheets.append(kmap.info["sheet"])
            kmap = None  # one Keyword Map serves the first Plan sheet
        first = first or t
    if first is None:
        found = "; ".join(f"[{t.info['sheet'] or src}] {', '.join(t.info['columns'].values())}" for t in tables)
        raise SystemExit(f"--prior {src}: no grouped layout found. Expected a keyword column with a group column "
                         "(long), a main keyword column with a secondary keyword column (wide or one keyword per "
                         f"row), or the team's final plan (Plan sheet). Columns found: {found}")
    if len({r["sheet"] for r in records}) > 1:  # STT 1 of 'Christmas' is not STT 1 of 'Halloween'
        for r in records:
            r["group"] = f"{r['sheet']}: {r['group']}"
    info = dict(first.info)
    info.update(layout="+".join(dict.fromkeys(layouts)), groups=len({r["group_key"] for r in records}),
                keywords=len(records), sheets=[s for s in sheets if s], sheets_skipped=skipped, free=len(free),
                block_rows=sum(1 for r in records if r["layout"] == "block"))
    return records + free, info
