#!/usr/bin/env python3
"""Dựng bản đồ pillar/cluster từ clusters.csv (đầu ra của keyword-clustering). Chỉ dùng thư viện chuẩn.

Đầu ra: <out>/topic-map.csv  và  <out>/topic-map.md

Quy tắc chính:
  * Mỗi cụm thuộc đúng MỘT pillar, chọn theo thứ tự ưu tiên facet (--priority, mặc định
    occasion,interest,recipient,craft). Facet còn lại dùng để link chéo (internal-link-planner).
  * Pillar cần >= --min-clusters cụm; ít hơn thì cụm đứng riêng (standalone) và chỉ gợi ý pillar cha.
  * Cụm có blog_fit = low (ý định mua hàng thuần túy) bị đánh dấu skip, không đưa vào bản đồ blog.
  * Điểm ưu tiên = cluster_volume x trọng số blog_fit x (0.5 + khả thi), khả thi = 1 - KD/100
    (KD thiếu -> 0.5). Đây là heuristic để xếp hạng, không phải số đo của Google.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
TAXONOMY_CANDIDATES = [
    os.path.join(HERE, "..", "assets", "taxonomy.json"),
    os.path.join(HERE, "..", "..", "keyword-clustering", "assets", "taxonomy.json"),
]
FIT_WEIGHT = {"high": 1.0, "medium": 0.6, "low": 0.15}
GENERIC_RECIPIENTS = {"her", "him"}  # quá rộng để làm pillar
KNOWHOW_NEEDS = {"how_to", "solve", "info"}
LIST_NEEDS = {"inspire", "choose"}
EXPECTED_BY_TYPE = {
    "occasion": ["list", "copy_ideas", "info"],
    "interest": ["list", "copy_ideas", "how_to|solve"],
    "recipient": ["list", "copy_ideas"],
    "craft": ["how_to|solve", "info|choose"],
    "product": ["list", "how_to|solve"],
}
GAP_HINT = {
    "list": "gift guide theo người nhận/ngân sách",
    "copy_ideas": "slogan / quote / caption / lời nhắn thiệp",
    "info": "what is / when is / ý nghĩa / lịch sử",
    "how_to": "how to cá nhân hóa / thiết kế / chăm sóc",
    "solve": "xử lý vấn đề: giặt, co rút, chọn size",
    "choose": "best X / X vs Y / cách chọn",
}


def load_taxonomy(path: str | None) -> dict | None:
    for cand in ([path] if path else TAXONOMY_CANDIDATES):
        if cand and os.path.exists(cand):
            with open(cand, encoding="utf-8") as fh:
                return json.load(fh)
    return None


def prettify(key: str) -> str:
    return " ".join(w.capitalize() for w in key.replace("-", " ").split())


def pillar_title(ptype: str, key: str, market: str, tax: dict | None) -> str:
    if ptype == "product" and tax and key in tax["facets"]["product"]["values"]:
        return f"{tax['facets']['product']['values'][key]['label']}: Ideas & Guides"
    if ptype == "product":
        return f"{prettify(key)}: Ideas & Guides"
    if tax and ptype in tax["facets"] and key in tax["facets"][ptype].get("values", {}):
        spec = tax["facets"][ptype]["values"][key]
        label = spec.get("label_uk") if market == "uk" and spec.get("label_uk") else spec["label"]
        tpl = tax["facets"][ptype].get("title_template", "{label}")
        return tpl.format(label=label)
    if ptype == "occasion":
        return f"{prettify(key)} Gift Ideas"
    if ptype in ("interest", "recipient"):
        return f"Gift Ideas for {prettify(key)}"
    if ptype == "craft":
        return f"{prettify(key)} Guide"
    if ptype == "inspiration":
        return "Slogans, Quotes & Caption Ideas"
    return prettify(key)


def slugify(text: str) -> str:
    s = text.lower().replace("’", "").replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > 60:
        s = s[:60].rsplit("-", 1)[0]
    return s


def to_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def stage_key(row: dict, stage: str) -> str:
    """Khóa pillar của một cụm ở một 'tầng' ưu tiên; rỗng nghĩa là cụm không thuộc tầng này."""
    need = row["reader_need"]
    if stage in ("occasion", "interest", "recipient") and row.get("craft") and need in KNOWHOW_NEEDS:
        return ""  # bài kiến thức (giặt, size, in ấn) thuộc pillar craft, không thuộc pillar đối tượng
    if stage == "recipient" and row.get("recipient") in GENERIC_RECIPIENTS:
        return ""
    if stage == "craft":
        if row.get("craft"):
            return row["craft"]
        return (row.get("product") or "") if need in ("how_to", "solve") else ""
    if stage == "inspiration":
        return "copy-ideas" if need == "copy_ideas" else ""
    return row.get(stage) or ""


def stage_type(stage: str) -> str:
    return stage


def assign_groups(live: list[dict], priority: list[str], min_clusters: int):
    """Gán cụm vào pillar theo từng tầng: tầng nào có >= min_clusters cụm cùng khóa thì thành pillar,
    cụm còn lại rơi xuống tầng kế tiếp. Cụm không tầng nào nhận thì đứng riêng."""
    stages = priority + [s for s in ("inspiration", "product") if s not in priority]
    groups: dict[tuple, list[dict]] = {}
    remaining = list(live)
    for stage in stages:
        buckets: dict[tuple, list[dict]] = defaultdict(list)
        for r in remaining:
            key = stage_key(r, stage)
            if key:
                buckets[(r["market"], key)].append(r)
        taken = set()
        for (market, key), members in buckets.items():
            if len(members) >= min_clusters:
                groups[(market, stage_type(stage), key)] = members
                taken.update(id(m) for m in members)
        remaining = [r for r in remaining if id(r) not in taken]
    return groups, remaining


def post_type(row: dict, is_pillar: bool) -> str:
    if is_pillar:
        return "pillar-hub"
    need = row["reader_need"]
    has_gift_facet = any(row.get(f) for f in ("occasion", "recipient", "interest"))
    if need == "inspire":
        return "gift-guide" if has_gift_facet else "ideas-list"
    if need == "choose":
        return "gift-guide" if has_gift_facet and "gift" in row["cluster_name"].lower() else "choose-guide"
    return {"how_to": "how-to", "solve": "how-to", "copy_ideas": "copy-ideas",
            "info": "explainer", "shop": "skip"}.get(need, "explainer")


def priority_score(row: dict) -> int:
    kd = to_int(row.get("seed_kd"), -1)
    achievable = 0.5 if kd < 0 else max(0.0, 1 - kd / 100)
    return round(to_int(row["cluster_volume"]) * FIT_WEIGHT.get(row["blog_fit"], 0.6) * (0.5 + achievable))


def choose_pillar_cluster(rows: list[dict], own_facet: str) -> dict | None:
    eligible = [r for r in rows if r["reader_need"] in LIST_NEEDS and r["blog_fit"] == "high"]
    if not eligible:
        return None

    def specificity(r):
        return sum(1 for f in ("occasion", "recipient", "interest", "product", "craft")
                   if f != own_facet and r.get(f))
    return sorted(eligible, key=lambda r: (specificity(r), -to_int(r["cluster_volume"])))[0]


def has_need(needs: set[str], spec: str) -> bool:
    for alt in spec.split("|"):
        if alt == "list":
            if needs & LIST_NEEDS:
                return True
        elif alt in needs:
            return True
    return False


def build(rows: list[dict], priority: list[str], min_clusters: int, tax: dict | None):
    live = [r for r in rows if r["blog_fit"] != "low"]
    skipped = [r for r in rows if r["blog_fit"] == "low"]
    real, leftovers = assign_groups(live, priority, min_clusters)

    out, gaps, used_slugs = [], {}, set()

    def unique_slug(text: str) -> str:
        base, n, slug = slugify(text), 1, slugify(text)
        while slug in used_slugs:
            n += 1
            slug = f"{base}-{n}"
        used_slugs.add(slug)
        return slug

    ordered = sorted(real.items(), key=lambda kv: -sum(to_int(r["cluster_volume"]) for r in kv[1]))
    pillar_ids = {}
    for n, ((market, ptype, key), members) in enumerate(ordered, 1):
        pid = f"P{n:02d}"
        pillar_ids[(market, ptype, key)] = pid
        title = pillar_title(ptype, key, market, tax)
        chosen = choose_pillar_cluster(members, ptype)
        total = sum(to_int(r["cluster_volume"]) for r in members)
        seasons = {r.get("season", "") for r in members if r.get("season")}
        base = {"pillar_id": pid, "pillar_type": ptype, "pillar_key": key, "pillar_name": title, "market": market}
        if chosen:
            out.append({**base, "role": "pillar", "cluster_id": chosen["cluster_id"],
                        "primary_keyword": chosen["cluster_name"], "planned_slug": unique_slug(chosen["cluster_name"]),
                        "post_type": "pillar-hub", "reader_need": chosen["reader_need"],
                        "cluster_volume": to_int(chosen["cluster_volume"]), "priority_score": priority_score(chosen),
                        "season": chosen.get("season", ""), "occasion": chosen.get("occasion", ""),
                        "recipient": chosen.get("recipient", ""), "interest": chosen.get("interest", ""),
                        "product": chosen.get("product", ""), "craft": chosen.get("craft", ""),
                        "keywords": chosen["keywords"], "parent_hint": "",
                        "note": f"pillar chọn từ cụm {chosen['cluster_id']}; viết như hub bao quát các cluster bên dưới"})
        else:
            out.append({**base, "role": "pillar", "cluster_id": "", "primary_keyword": title.lower(),
                        "planned_slug": unique_slug(title), "post_type": "pillar-hub", "reader_need": "inspire",
                        "cluster_volume": 0, "priority_score": round(total * 0.3),
                        "season": next(iter(seasons)) if len(seasons) == 1 else "", "occasion": "", "recipient": "",
                        "interest": "", "product": "", "craft": "", "keywords": "", "parent_hint": "",
                        "note": "pillar ẢO: không cụm nào đủ rộng; nghiên cứu keyword đầu mối rồi viết hub"})
        for r in sorted(members, key=lambda r: -to_int(r["cluster_volume"])):
            if chosen and r["cluster_id"] == chosen["cluster_id"]:
                continue
            out.append({**base, "role": "cluster", "cluster_id": r["cluster_id"], "primary_keyword": r["cluster_name"],
                        "planned_slug": unique_slug(r["cluster_name"]), "post_type": post_type(r, False),
                        "reader_need": r["reader_need"], "cluster_volume": to_int(r["cluster_volume"]),
                        "priority_score": priority_score(r), "season": r.get("season", ""),
                        "occasion": r.get("occasion", ""), "recipient": r.get("recipient", ""),
                        "interest": r.get("interest", ""), "product": r.get("product", ""), "craft": r.get("craft", ""),
                        "keywords": r["keywords"], "parent_hint": "", "note": ""})
        needs = {r["reader_need"] for r in members}
        if ptype in EXPECTED_BY_TYPE:
            missing = [s for s in EXPECTED_BY_TYPE[ptype] if not has_need(needs, s)]
            if missing:
                gaps[pid] = [(s, GAP_HINT[s.split("|")[0]]) for s in missing]

    keys_by_market = {(m, k): pid for (m, t, k), pid in pillar_ids.items()}
    for r in sorted(leftovers, key=lambda r: -to_int(r["cluster_volume"])):
        hint = ""
        for facet in ("interest", "recipient", "occasion", "craft", "product"):
            pid = keys_by_market.get((r["market"], r.get(facet, "")))
            if r.get(facet) and pid:
                hint = pid
                break
        out.append({"pillar_id": "", "pillar_type": "", "pillar_key": "", "pillar_name": "", "market": r["market"],
                    "role": "standalone", "cluster_id": r["cluster_id"], "primary_keyword": r["cluster_name"],
                    "planned_slug": unique_slug(r["cluster_name"]), "post_type": post_type(r, False),
                    "reader_need": r["reader_need"], "cluster_volume": to_int(r["cluster_volume"]),
                    "priority_score": priority_score(r), "season": r.get("season", ""),
                    "occasion": r.get("occasion", ""), "recipient": r.get("recipient", ""),
                    "interest": r.get("interest", ""), "product": r.get("product", ""), "craft": r.get("craft", ""),
                    "keywords": r["keywords"], "parent_hint": hint,
                    "note": "ít hơn %d cụm cùng nhóm: viết độc lập, link tới pillar gợi ý nếu có" % min_clusters})
    for r in sorted(skipped, key=lambda r: -to_int(r["cluster_volume"])):
        out.append({"pillar_id": "", "pillar_type": "", "pillar_key": "", "pillar_name": "", "market": r["market"],
                    "role": "skip", "cluster_id": r["cluster_id"], "primary_keyword": r["cluster_name"],
                    "planned_slug": "", "post_type": "skip", "reader_need": r["reader_need"],
                    "cluster_volume": to_int(r["cluster_volume"]), "priority_score": 0, "season": r.get("season", ""),
                    "occasion": r.get("occasion", ""), "recipient": r.get("recipient", ""),
                    "interest": r.get("interest", ""), "product": r.get("product", ""), "craft": r.get("craft", ""),
                    "keywords": r["keywords"], "parent_hint": "",
                    "note": "ý định mua hàng thuần túy: để trang bán hàng/ team content xử lý, không viết blog"})

    ranked = sorted((o for o in out if o["role"] != "skip"), key=lambda o: -o["priority_score"])
    for i, o in enumerate(ranked):
        pct = (i + 1) / max(1, len(ranked))
        o["bucket"] = "A" if pct <= 0.2 else "B" if pct <= 0.5 else "C"
    for o in out:
        o.setdefault("bucket", "")
    return out, gaps


FIELDS = ["pillar_id", "pillar_type", "pillar_key", "pillar_name", "role", "cluster_id", "primary_keyword",
          "planned_slug", "post_type", "reader_need", "cluster_volume", "priority_score", "bucket", "season",
          "market", "occasion", "recipient", "interest", "product", "craft", "keywords", "parent_hint", "note"]


def write_md(path: str, out: list[dict], gaps: dict) -> None:
    lines = ["# Topic map (pillar/cluster)", ""]
    by_pillar: dict[str, list[dict]] = defaultdict(list)
    for o in out:
        if o["pillar_id"]:
            by_pillar[o["pillar_id"]].append(o)
    for pid, rows in by_pillar.items():
        head = next(r for r in rows if r["role"] == "pillar")
        total = sum(r["cluster_volume"] for r in rows)
        season = f" · mùa vụ: {head['season']}" if head["season"] else ""
        lines += [f"## {pid} · {head['pillar_name']}  ({head['pillar_type']} · {head['market']}{season})",
                  f"Tổng volume các cụm: {total:,}. Pillar: `{head['planned_slug']}` – {head['primary_keyword']}"
                  + (" (pillar ảo)" if not head["cluster_id"] else ""), "",
                  "| Vai trò | Slug | Loại bài | Reader need | Volume | Ưu tiên |", "|---|---|---|---|---:|---|"]
        for r in rows:
            lines.append(f"| {r['role']} | `{r['planned_slug']}` | {r['post_type']} | {r['reader_need']} | "
                         f"{r['cluster_volume']:,} | {r['bucket']} |")
        if pid in gaps:
            lines += ["", "**Khoảng trống nội dung:** " + "; ".join(f"thiếu *{s.replace('|', ' hoặc ')}* ({h})" for s, h in gaps[pid])]
        lines.append("")
    stand = [o for o in out if o["role"] == "standalone"]
    if stand:
        lines += ["## Bài đứng riêng (chưa đủ cụm để lập pillar)", "",
                  "| Slug | Loại bài | Volume | Ưu tiên | Pillar gợi ý |", "|---|---|---:|---|---|"]
        lines += [f"| `{o['planned_slug']}` | {o['post_type']} | {o['cluster_volume']:,} | {o['bucket']} | {o['parent_hint'] or '-'} |"
                  for o in stand]
        lines.append("")
    skip = [o for o in out if o["role"] == "skip"]
    if skip:
        lines += ["## Bỏ qua (ý định mua hàng, không phải việc của blog)", ""]
        lines += [f"- {o['primary_keyword']} ({o['cluster_volume']:,})" for o in skip]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clusters", help="clusters.csv từ keyword-clustering")
    ap.add_argument("--out", default="outputs")
    ap.add_argument("--priority", default="occasion,interest,recipient,craft",
                    help="thứ tự facet quyết định pillar (mặc định: occasion,interest,recipient,craft)")
    ap.add_argument("--min-clusters", type=int, default=3)
    ap.add_argument("--taxonomy", default=None)
    args = ap.parse_args(argv)

    with open(args.clusters, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit("clusters.csv rỗng")
    tax = load_taxonomy(args.taxonomy)
    if tax is None:
        print("Không thấy taxonomy.json: tên pillar sẽ được suy ra từ key.", file=sys.stderr)
    priority = [p.strip() for p in args.priority.split(",") if p.strip()]
    out, gaps = build(rows, priority, args.min_clusters, tax)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "topic-map.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out)
    write_md(os.path.join(args.out, "topic-map.md"), out, gaps)
    n_p = len({o["pillar_id"] for o in out if o["pillar_id"]})
    counts = defaultdict(int)
    for o in out:
        counts[o["role"]] += 1
    print(f"{len(rows)} cụm -> {n_p} pillar | " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"Đã ghi vào: {os.path.abspath(args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
