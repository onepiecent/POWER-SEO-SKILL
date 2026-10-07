#!/usr/bin/env python3
"""Sheets of the final plan that show what each row rests on (module of export_plan.py; standard library only).

  Review       one row per STT: the data behind the post (tool intent, SERP features, grouping basis, the SEO's
               group, volumes, KD, outline seeds from the post's own keywords, open back-check issues, decisions)
  Back-check   backcheck.csv of keyword-clustering as it is, with the status updated from the decision logs
  Decisions    every row of the decision logs (decisions-log-<step>.csv), plus reason and evidence from the decisions file
  Not Planned  backlog, skip and merged-away clusters and the biggest excluded keywords: where each went and why

Every value comes from the input files; nothing is invented. A post without a reviewed angle shows 'unreviewed'.
"""
from __future__ import annotations

import csv
import re
import unicodedata
from collections import Counter

import table_io

REVIEW_COLUMNS = ["STT", "Market", "Main Keyword", "Post Type", "Reader Need", "Intent (tool)", "Need vs Intent",
                  "SERP Features (main)", "Grouping Basis", "SEO Group", "Main Volume", "Owned Volume", "Keywords",
                  "Biggest Keyword", "KD", "Outline Seeds (from this post's keywords)", "Angle (reviewed)",
                  "Open Issues", "Decisions Applied", "Why This Post"]
REVIEW_WIDTHS = [6, 7, 34, 13, 12, 24, 16, 28, 24, 20, 11, 11, 9, 36, 6, 64, 44, 28, 34, 56]
BACKCHECK_COLUMNS = ["issue_id", "check", "severity", "market", "group", "group_main", "keyword", "keyword_volume",
                     "other_group", "other_main", "evidence_type", "evidence", "proposed_action", "proposed_keyword",
                     "proposed_target", "proposed_value", "status"]
LOG_COLUMNS = ["decision_id", "step", "action", "market", "keyword", "target", "value", "author", "status", "detail"]
DECISIONS_COLUMNS = ["Decision ID", "Step", "Action", "Market", "Keyword", "Target", "Value", "Author", "Status",
                     "Detail", "Reason", "Evidence"]
DECISIONS_WIDTHS = [12, 8, 16, 7, 34, 34, 24, 10, 20, 50, 50, 60]
NOT_PLANNED_COLUMNS = ["Market", "Keyword or Cluster", "Volume", "Where It Went", "Reason", "Nearest Planned Post (STT)",
                       "Evidence"]
NOT_PLANNED_WIDTHS = [7, 40, 11, 44, 50, 40, 60]
APPLIED = ("applied", "applied_with_warning", "already_true")
QUOTES = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
                        "“": '"', "”": '"', "„": '"', "″": '"'})
MAX_SEEDS = 8
QUESTION_RX = re.compile(r"^(what|whats|when|where|why|how|who|which|can|do|does|did|is|are|was|were|should|will)\b")
# [Convention] tool intent labels compatible with each reader need (a Semrush/Ahrefs label is a hint, not proof)
NEED_INTENTS = {"inspire": {"informational", "commercial"}, "choose": {"commercial", "informational"},
                "how_to": {"informational"}, "solve": {"informational"}, "copy_ideas": {"informational"},
                "info": {"informational"}, "shop": {"transactional", "commercial"}}
WHERE = {"backlog": "backlog: not planned (long tail that matches no planned post)",
         "skip": "skipped: shopping intent (product or category pages, not the blog)"}


def decision_key(text: str) -> str:
    """Contract C1 matching key: NFC, lowercase, curly quotes straight, apostrophes removed, '-' and '_' as spaces."""
    t = unicodedata.normalize("NFC", str(text or "")).lower().translate(QUOTES)
    return " ".join(t.replace("'", "").replace("-", " ").replace("_", " ").split())


def to_int(v, default=None):
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return default


def read_rows(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def read_decisions(path: str) -> list[dict]:
    """The decisions file (contract C1): a CSV, or an .xlsx whose sheet Decisions (else the first sheet) has the headers."""
    if path.lower().endswith((".xlsx", ".xlsm")):
        try:
            return table_io.read_table(path, {"decision_id"}, sheet="Decisions")
        except SystemExit:
            pass
    return table_io.read_table(path, {"decision_id"})


def same_market(a: str, b: str) -> bool:
    return not a or not b or a == "all" or b == "all" or a == b


def backcheck_status(issues: list[dict], logs: list[dict], decisions: list[dict] | None = None) -> list[dict]:
    """status = decided:<decision_id> when an applied decision answers the issue (its source_issue in the decisions
    file, its id naming the issue, or the same action, keyword and target as the proposal); else unchanged."""
    source = {d.get("decision_id", ""): set(re.split(r"[\s|,;]+", d.get("source_issue") or "")) - {""}
              for d in decisions or []}  # one decision may settle several issues: 'BC-1|BC-2'
    out = []
    for issue in issues:
        row, iid = dict(issue), issue.get("issue_id", "")
        for log in logs:
            did = log.get("decision_id", "")
            if log.get("status") not in APPLIED or not iid or not did:
                continue
            same_proposal = (issue.get("proposed_action") and log.get("action") == issue.get("proposed_action")
                             and decision_key(log.get("keyword")) == decision_key(issue.get("proposed_keyword"))
                             and decision_key(log.get("target")) == decision_key(issue.get("proposed_target"))
                             and same_market(log.get("market", ""), issue.get("market", "")))
            if iid in source.get(did, ()) or iid in did or same_proposal:
                row["status"] = f"decided:{did}"
        out.append(row)
    return out


def decision_rows(logs: list[dict], decisions: list[dict] | None = None) -> list[list]:
    by_id = {d.get("decision_id", ""): d for d in decisions or []}
    return [[log.get(c, "") for c in LOG_COLUMNS] + [by_id.get(log.get("decision_id", ""), {}).get("reason", ""),
                                                      by_id.get(log.get("decision_id", ""), {}).get("evidence", "")]
            for log in logs]


def need_vs_intent(need: str, intents: str, need_source: str) -> str:
    labels = {x for x in (intents or "").split("|") if x}
    verdict = ("no tool label" if not labels else
               "agree" if labels & NEED_INTENTS.get(need, set()) else "conflict")
    return f"{verdict} ({need_source})" if (need_source or "").startswith("conflict") else verdict


def grouping_basis(own: list[dict], merged: int) -> str:
    """From keyword-map's joined_by (seed, serp:<n>, parent, lexical:<sim>, core:<words>), as clusters.csv names it."""
    kinds = set()
    for k in own:
        kind = (k.get("joined_by") or "").split(":")[0]
        if kind and kind != "seed":
            kinds.add({"parent": "parent_topic", "core": "lexical"}.get(kind, kind))
    basis = ("single" if len(own) <= 1 else "" if not kinds else "lexical (not verified by SERP)" if kinds == {"lexical"}
             else next(iter(kinds)) if len(kinds) == 1 else "mixed")
    return basis + (f"; + {merged} merged cluster(s) (topic-map)" if merged else "")


def verified_share(own: list[dict], kws: list[dict]) -> float | None:
    """Share of the post's volume (kws: its cluster and the clusters merged into it) whose membership rests on shared
    SERP URLs or the Parent Topic within its own cluster (the seed counts once a member is verified; a merged
    cluster joined by topic-map, not by SERP); None when the keyword map has no joined_by data."""
    total = sum(to_int(k.get("volume"), 0) for k in kws)
    if not total or not any(k.get("joined_by") for k in kws):
        return None
    verified = sum(to_int(k.get("volume"), 0) for k in own if (k.get("joined_by") or "").startswith(("serp", "parent")))
    if verified:
        verified += sum(to_int(k.get("volume"), 0) for k in own if k.get("joined_by") == "seed")
    return verified / total


def outline_seeds(main: str, kws: list[dict], signature, light: set[str]) -> list[str]:
    """The post's own keywords that ask something new: new words versus the main keyword, or a question when the main
    keyword is not one. Largest first, with their real volumes; never a keyword that is not in the data."""
    main_sig = signature(main)
    main_question = bool(QUESTION_RX.match(main.lower()))
    seen, out = {main_sig}, []
    for k in sorted(kws, key=lambda k: -(to_int(k.get("volume"), 0))):
        kw, sig = k["keyword"], signature(k["keyword"])
        if kw == main or k.get("spelling_fixed", "0") == "1" or not sig or sig in seen:
            continue
        new_words = (sig - light) - main_sig
        if not new_words and (main_question or not QUESTION_RX.match(kw.lower())):
            continue
        seen.add(sig)
        vol = to_int(k.get("volume"))
        out.append(f"H2 candidate: {kw} ({vol:,}/mo)" if vol is not None else f"H2 candidate: {kw} ([DATA NEEDED: volume])")
        if len(out) >= MAX_SEEDS:
            break
    return out


def review_rows(plan, rows: list[dict], signature, light: set[str], issues: list[dict] | None = None,
                logs: list[dict] | None = None) -> list[list]:
    angle_of = getattr(plan, "angle_of", {}) or {}
    out = []
    for r in rows:
        post, n = r["post"], r["n"]
        slug, market, main_kw = post["planned_slug"], post.get("market", ""), post["primary_keyword"]
        own = plan.kw_by_cluster.get(post["cluster_id"], [])
        kws = plan.keywords_of(post)
        main = next((k for k in kws if k["keyword"] == main_kw), {})
        keys = {decision_key(k["keyword"]) for k in kws} | {decision_key(v["keyword"]) for k in kws
                                                             for v in plan.variants_of(k)}
        merged = plan.merged_into.get(slug, [])
        owned = to_int(post.get("cluster_volume"), 0) + sum(to_int(m.get("cluster_volume"), 0) for m in merged)
        groups = [g for g in [main.get("prior_group", "")] + [k.get("prior_group", "") for k in kws] if g]
        biggest = max((k for k, _ in r["roles"]), key=lambda k: to_int(k.get("volume"), 0), default=None)
        big_vol = to_int(biggest.get("volume")) if biggest else None
        issue_ids = [f"{i['issue_id']} {i.get('check', '')} ({i.get('severity', '')})" for i in issues or []
                     if i.get("status", "open") == "open" and same_market(i.get("market", ""), market)
                     and {decision_key(i.get(c, "")) for c in ("keyword", "group_main", "other_main")} & keys]
        applied, seen = [], set()
        for log in logs or []:
            did = log.get("decision_id", "")
            on_post = ({decision_key(log.get("keyword", "")), decision_key(log.get("target", ""))} & keys
                       or log.get("keyword", "").replace(" ", "").lower() == f"stt:{n}")
            if log.get("status") in APPLIED and on_post and same_market(log.get("market", ""), market) and did not in seen:
                seen.add(did)
                applied.append(f"{did} {log.get('action', '')} ({log.get('status')})")
        for k in kws:  # ids recorded in keyword-map.csv by the cluster step
            for did in (k.get("decision_ids") or "").split("|"):
                if did and did not in seen:
                    seen.add(did)
                    applied.append(did)
        raw_share = post.get("serp_verified_share")
        share = float(raw_share) if raw_share not in (None, "") else verified_share(own, kws)
        why = [f"owns {len(r['roles'])} keywords, {owned:,}/mo"]
        if share is not None:
            why.append(f"SERP-verified {round(share * 100)}% of the volume")
        if post.get("bucket"):
            why.append(f"priority {post['bucket']} (score {post.get('priority_score', '')})")
        angle = angle_of.get(slug) or angle_of.get(n) or angle_of.get(str(n)) or angle_of.get(decision_key(main_kw))
        out.append([n, market, main_kw, post.get("post_type", ""), post.get("reader_need", ""),
                    (main.get("intents") or "").replace("|", ", ") or "no tool label",
                    need_vs_intent(post.get("reader_need", ""), main.get("intents", ""), main.get("need_source", "")),
                    (main.get("serp_features") or "").replace("|", ", "),
                    post.get("grouping_basis") or grouping_basis(own, len(merged)),
                    " | ".join(dict.fromkeys(groups)),
                    to_int(main.get("volume"), ""), owned, len(r["roles"]),
                    f"{biggest['keyword']} ({big_vol:,}/mo)" if biggest and big_vol is not None else "",
                    r["kd"] if r["kd"] is not None else "",
                    "\n".join(outline_seeds(main_kw, kws, signature, light)),
                    angle or "unreviewed", "\n".join(issue_ids), "\n".join(applied), "; ".join(why)])
    return out


def not_planned_rows(plan, topic: list[dict], excluded: list[dict], signature, max_excluded: int = 300) -> list[list]:
    """Backlog, skip and merged-away clusters of the topic map, then the biggest excluded keywords; each with where
    it went, the reason and the planned post sharing the most non-topic words with it (the shared words shown)."""
    mains = {plan.stt[p["planned_slug"]]: p for p in plan.posts}
    words = Counter(w for p in plan.posts for w in signature(p["primary_keyword"]))
    topic_words = {w for w, c in words.items() if len(plan.posts) >= 3 and c >= 0.5 * len(plan.posts)}
    post_words = {n: (set(signature(p["primary_keyword"])) | {w for k in p.get("keywords", "").split("|")[:15]
                                                              for w in signature(k)}) - topic_words
                  for n, p in mains.items()}

    def nearest(keyword: str, market: str) -> str:
        mine = set(signature(keyword)) - topic_words
        best = max(((len(mine & ws), -n) for n, ws in post_words.items()
                    if same_market(market, mains[n].get("market", ""))), default=(0, 0))
        if not best[0]:
            return ""
        n = -best[1]
        return f"{n} ({mains[n]['primary_keyword']}; shared: {', '.join(sorted(mine & post_words[n]))})"

    out = []
    for r in sorted((r for r in topic if r.get("role") in ("backlog", "skip", "merged")),
                    key=lambda r: -to_int(r.get("cluster_volume"), 0)):
        kws = [k for k in (r.get("keywords") or "").split("|") if k]
        evidence = (f"cluster {r.get('cluster_id', '')}, reader need {r.get('reader_need', '') or '-'}, "
                    f"{len(kws)} keyword(s): " + ", ".join(kws[:5]))
        if r["role"] == "merged":
            target = r.get("merged_into", "")
            n = plan.stt.get(target)
            where = (f"merged into STT {n} ({next(p for p in plan.posts if p['planned_slug'] == target)['primary_keyword']})"
                     if n is not None else f"merged into {target or 'another post'}")
            near = str(n) if n is not None else ""
        else:
            where, near = WHERE[r["role"]], nearest(r.get("primary_keyword", ""), r.get("market", ""))
        out.append([r.get("market", ""), r.get("primary_keyword", ""), to_int(r.get("cluster_volume"), ""), where,
                    r.get("note", ""), near, evidence])
    for e in sorted(excluded, key=lambda e: -to_int(e.get("volume"), 0))[:max_excluded]:
        out.append([e.get("market", ""), e.get("keyword", ""), to_int(e.get("volume"), ""),
                    "excluded before clustering (excluded.csv)", e.get("reason", ""),
                    nearest(e.get("keyword", ""), e.get("market", "")),
                    f"source: {e.get('source_file', '')}" if e.get("source_file") else ""])
    return out
