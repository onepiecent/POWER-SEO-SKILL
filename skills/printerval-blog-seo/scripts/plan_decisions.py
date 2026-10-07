"""Decisions of the export step (shared decisions contract, references/data-contracts.md). Standard library only.

  * set_category / set_title / set_meta / set_outline fill the EMPTY team cell of a post (keyword = its Main Keyword or
    'STT:<n>'); a value the team typed (from --previous) always wins: logged team_value_kept. A cell that still holds
    what a decision wrote on an earlier run (the previous workbook's Decisions sheet) belongs to that decision: a
    changed value replaces it, and a decision removed from the file clears it (logged withdrawn).
  * set_angle stores the reviewed angle per post in plan.angle_of[slug] (Review sheet).
  * research_seed adds a Research Next row (status 'unverified: export volume (same market)'), never a Plan row.
Actions of the cluster and topic steps are not logged here; an action no step knows is logged invalid by the export
step only when it runs on its own (with run_plan the cluster step already logs it).
"""
from __future__ import annotations

import csv
import os
import re
import unicodedata
from collections import defaultdict

import table_io

EXPORT_ACTIONS = ("set_category", "set_title", "set_meta", "set_outline", "set_angle", "research_seed")
OTHER_STEPS = ("drop_keyword", "keep_keyword", "set_need", "merge", "move_keyword", "split", "keep_apart", "rename_main",
               "veto_respell", "set_pillar", "promote_pillar", "demote_pillar", "restore_backlog", "drop_post")
CELL_OF = {"set_category": "Category", "set_title": "Title SEO", "set_meta": "Meta Description SEO", "set_outline": "Outline"}
LOG_FIELDS = ["decision_id", "step", "action", "market", "keyword", "target", "value", "author", "status", "detail"]
RESEARCH_STATUS = "unverified: export volume (same market)"
QUOTES = str.maketrans({"‘": "'", "’": "'", "ʼ": "'", "“": '"', "”": '"'})


def decision_key(text: str) -> str:
    """Matching key of the decisions contract: NFC, lowercase, straight quotes, no apostrophes, '-'/'_' as spaces."""
    t = unicodedata.normalize("NFC", text or "").lower().translate(QUOTES).replace("'", "")
    return " ".join(t.replace("-", " ").replace("_", " ").split())


def csv_delimiter(path: str) -> str:
    """The delimiter of the header line (the one with decision_id): ',' or ';' (Excel with Vietnamese or European
    regional settings) or a tab. Never guessed from the whole file: 'BC-1|BC-2' in source_issue is not a delimiter."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for line in fh:
            if "decision_id" in line.lower():
                return max(",;\t", key=line.count)
    return ","


def norm_market(raw: str) -> str:
    """us, uk ('gb', 'united kingdom'...) or '' (any market: '', 'all')."""
    s = (raw or "").strip().lower()
    return {"gb": "uk", "united kingdom": "uk", "great britain": "uk", "united states": "us", "usa": "us",
            "all": ""}.get(s, s)


def read_decisions(path: str) -> list[dict]:
    """Rows of a decisions file (CSV, or the .xlsx sheet 'Decisions' or first sheet), keyed by lowercase header.
    The one reader of the export step (the Plan and Review sheets both use it)."""
    wanted = {"decision_id"}
    if path.lower().endswith((".xlsx", ".xlsm")):
        try:
            rows = table_io.read_table(path, wanted, sheet="Decisions")
        except SystemExit:
            rows = table_io.read_table(path, wanted)
    else:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            raw = list(csv.reader(fh, delimiter=csv_delimiter(path)))
        h = next((i for i, r in enumerate(raw) if "decision_id" in {c.strip().lower() for c in r}), None)
        if h is None:
            raise SystemExit(f"{path}: no header with decision_id")
        rows = [dict(zip(raw[h], r)) for r in raw[h + 1:]]
    out = []
    for r in rows:
        d = {str(k).strip().lower(): str(v if v is not None else "").strip() for k, v in r.items() if k}
        if any(d.values()):
            out.append(d)
    return out


def previous_values(rows: list[dict]) -> dict[tuple, dict]:
    """{(decision_id, cell): value} of the set_* decisions applied on the previous run (its Decisions sheet)."""
    out = {}
    for r in rows:
        low = {str(k).strip().lower(): str(v or "").strip() for k, v in r.items()}
        action = low.get("action", "")
        if low.get("step") == "export" and action in CELL_OF and low.get("status", "") in (
                "applied", "applied_with_warning", "already_true"):  # the cell still held the decision's value
            out[(low.get("decision id") or low.get("decision_id", ""), CELL_OF[action])] = {
                "value": low.get("value", "").replace("\\n", "\n"), "keyword": low.get("keyword", ""),
                "market": low.get("market", ""), "action": action}
    return out


def apply(decisions: list[dict], plan, rows: list[dict], previous: dict | None = None,
          log_unknown: bool = True) -> tuple[list[dict], list[list]]:
    """Apply the export step's decisions to the plan (plan.team, plan.angle_of) in decision_id order.
    rows are plan.rows() with the final STT; previous = previous_values() of the previous workbook. Returns (log rows,
    extra Research Next rows)."""
    if not hasattr(plan, "angle_of"):
        plan.angle_of = {}
    by_stt = {r["n"]: r for r in rows}
    by_main: dict[str, list[dict]] = defaultdict(list)
    by_kw: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_main[decision_key(r["post"]["primary_keyword"])].append(r)
        for k, _ in r.get("roles", []):
            if not any(x is r for x in by_kw[decision_key(k["keyword"])]):
                by_kw[decision_key(k["keyword"])].append(r)

    def find(text: str, market: str):
        m = re.fullmatch(r"\s*stt\s*:\s*(\d+)\s*", text or "", re.I)
        if m:
            r = by_stt.get(int(m.group(1)))
            return (r, "", "") if r else (None, "stale", f"no post with STT {m.group(1)}")
        key = decision_key(text)
        ok = lambda r: not market or r["post"]["market"] in (market, "all")  # noqa: E731
        hits = [r for r in by_main.get(key, []) if ok(r)]
        hits = hits or [r for r in by_kw.get(key, []) if ok(r)]
        if len({r["post"]["market"] for r in hits}) > 1:
            return None, "invalid", f"'{text}' is in several markets: set market"
        if hits:
            return hits[0], "", ""
        words = set(key.split())
        pool = [r for r in rows if ok(r)]
        shared = lambda r: len(words & set(decision_key(r["post"]["primary_keyword"]).split()))  # noqa: E731
        close = max(pool, key=lambda r: (shared(r), r["volume"] or 0), default=None)
        return None, "stale", f"'{text}' not found" + (f"; closest: '{close['post']['primary_keyword']}' (STT {close['n']})"
                                                       if close and shared(close) else "; no post shares a word with it")

    log, todo = [], []
    for d in decisions:
        action = (d.get("action") or "").strip().lower()
        if action in OTHER_STEPS or (action not in EXPORT_ACTIONS and not log_unknown):
            continue  # another step's action (or an unknown one the cluster step already logged)
        e = {"decision_id": d.get("decision_id", ""), "step": "export", "action": action,
             "market": norm_market(d.get("market")), "keyword": d.get("keyword", ""),
             "target": d.get("target", ""), "value": d.get("value", ""), "author": d.get("author", ""),
             "status": "", "detail": ""}
        log.append(e)
        if action not in EXPORT_ACTIONS:
            e.update(status="invalid", detail=f"unknown action '{action}'")
        elif (d.get("author") or "").strip().lower() == "proposal":
            e.update(status="invalid", detail="author 'proposal': a back-check proposal is never applied as it is")
        elif not (d.get("reason") or "").strip() or not (d.get("evidence") or "").strip():
            e.update(status="invalid", detail="reason and evidence are required")
        elif e["market"] not in ("", "us", "uk"):
            e.update(status="invalid", detail=f"unknown market '{e['market']}'")
        elif not (e["value"] or "").strip() and action != "research_seed":
            e.update(status="invalid", detail="value is empty")
        else:
            todo.append(e)
    research, targets = [], defaultdict(list)
    for e in sorted(todo, key=lambda e: e["decision_id"]):
        if e["action"] == "research_seed":
            seeds = [s.strip() for s in re.split(r"[|\n]", e["value"] or e["keyword"]) if s.strip()]
            if not seeds:
                e.update(status="invalid", detail="no seed keyword (value or keyword)")
                continue
            reason = next((d.get("reason", "") for d in decisions if d.get("decision_id") == e["decision_id"]), "")
            research.append([e["keyword"] or seeds[0], "decision " + e["decision_id"], reason, "", "", RESEARCH_STATUS,
                             "\n".join(seeds), ""])
            e.update(status="applied", detail=f"Research Next row ({len(seeds)} seed(s)), not a Plan row")
            continue
        r, status, detail = find(e["keyword"], e["market"])
        if r is None:
            e.update(status=status, detail=detail)
            continue
        e["market"] = r["post"]["market"]
        targets[(r["n"], e["action"])].append((e, r))
    for (n, action), group in targets.items():
        if len({(e["value"] or "").strip() for e, _ in group}) > 1:  # two different values for one cell
            for e, _ in group:
                e.update(status="conflict", detail=f"STT {n}: conflicts with " + ", ".join(
                    x["decision_id"] for x, _ in group if x is not e))
            continue
        for i, (e, r) in enumerate(group):
            slug, value = r["post"]["planned_slug"], e["value"].replace("\\n", "\n").strip()
            if action == "set_angle":
                if i or plan.angle_of.get(slug) == value:
                    e.update(status="already_true", detail=f"STT {n}: same angle already set")
                else:
                    plan.angle_of[slug] = value
                    e.update(status="applied", detail=f"STT {n}: Angle (reviewed)")
                continue
            col = CELL_OF[action]
            current = (plan.team.get(slug, {}).get(col) or "").strip()
            mine = (previous or {}).get((e["decision_id"], col), {}).get("value", "").strip()
            if current == value:
                e.update(status="already_true", detail=f"STT {n}: {col} already holds this value")
            elif current and current != mine:
                e.update(status="team_value_kept", detail=f"STT {n}: skipped: the team's value wins: '{current[:60]}'")
            else:
                plan.team.setdefault(slug, {})[col] = value
                e.update(status="applied", detail=f"STT {n}: {col} " + ("replaced (the decision's value changed)"
                                                                        if current else "filled"))
    # a decision removed from the file: the value it wrote last run is cleared if nobody edited it since
    current_ids = {d.get("decision_id", "") for d in decisions}
    for (did, col), old in (previous or {}).items():
        if did in current_ids or not old["value"]:
            continue
        r, _, _ = find(old["keyword"], norm_market(old["market"]))
        if r is None:
            continue
        slug = r["post"]["planned_slug"]
        if (plan.team.get(slug, {}).get(col) or "").strip() == old["value"].strip():
            plan.team[slug][col] = ""
            log.append({"decision_id": did, "step": "export", "action": old["action"], "market": r["post"]["market"],
                        "keyword": old["keyword"], "target": "", "value": "", "author": "", "status": "withdrawn",
                        "detail": f"STT {r['n']}: {col} cleared: the decision is no longer in the decisions file"})
    return log, research


def write_log(path: str, log: list[dict]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LOG_FIELDS)
        w.writeheader()
        w.writerows(log)


def summary(log: list[dict]) -> str:
    counts = defaultdict(int)
    for e in log:
        counts[e["status"]] += 1
    return f"Decisions (export step): {len(log)} logged" + "".join(f", {k} {v}" for k, v in sorted(counts.items()))
