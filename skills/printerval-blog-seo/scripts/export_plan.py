#!/usr/bin/env python3
"""Export the final keyword plan for the content team (one row per blog post). Standard library only.

    export_plan.py --topic-map outputs/topic-map.csv --keyword-map outputs/keyword-map.csv \
                   --link-plan outputs/link-plan.csv --out outputs/final-plan.xlsx

Columns (the team's template, in this order):
  STT | Main Keyword | Secondary Keyword | Volume | KD | Category | Category Kind | Thuộc Pillar | Title SEO |
  Meta Description SEO | Outline | Internal Link (Anchor || URL) | Related Post (Anchor || URL) | URL Blog | Trạng thái

  * Category, Title SEO, Meta Description SEO, Outline and Trạng thái are left empty: the content team fills them.
  * Category Kind is Pillar or Cluster; a Cluster names its pillar (the pillar's main keyword) in Thuộc Pillar.
  * Volume and KD are those of the main keyword (--volume post puts the post's total instead, an upper bound).
  * Secondary Keyword: the post's other keywords (including clusters merged into it), largest first, without
    duplicates that only differ by word order, a year or a fixed typo.
  * URL Blog is the PLANNED URL (--url-pattern). In the .xlsx the two link columns are formulas that read URL Blog
    of the target row (matched by STT), so pasting the real URL after publishing updates every link to that post.
    The .csv copy has plain text.

A second sheet, Keyword Map, lists every keyword placed in the plan and the post (STT) it belongs to.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import re
import sys
import zipfile
from collections import defaultdict
from xml.sax.saxutils import escape

COLUMNS = ["STT", "Main Keyword", "Secondary Keyword", "Volume", "KD", "Category", "Category Kind", "Thuộc Pillar",
           "Title SEO", "Meta Description SEO", "Outline", "Internal Link (Anchor || URL)",
           "Related Post (Anchor || URL)", "URL Blog", "Trạng thái"]
COL = {name: i for i, name in enumerate(COLUMNS)}
WIDTHS = [6, 34, 44, 11, 6, 16, 14, 30, 30, 34, 30, 60, 60, 46, 14]
MAP_COLUMNS = ["STT", "Main Keyword", "Keyword", "Volume", "KD", "Role"]
MAP_WIDTHS = [6, 40, 52, 11, 6, 14]
PLANNED = ("pillar", "cluster", "standalone")
BODY_LINKS = ("to_pillar", "cross_pillar", "from_pillar", "orphan_fix", "related", "backlink_old_post")
STOP = {"the", "a", "an", "of", "in", "on", "for", "to", "is", "are", "was", "were", "do", "does", "did", "and"}
YEAR_RX = re.compile(r"^(19|20)\d\d$")
MAX_FORMULA = 8000
MAX_SECONDARY_WORDS = 8  # longer queries stay in the Keyword Map sheet ('also covers')


def read_csv(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def to_int(v, default=None):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def signature(keyword: str) -> frozenset:
    """Same words in another order, with a year or a plural: one secondary keyword is enough."""
    toks = re.sub(r"[^a-z0-9 ]+", " ", keyword.lower().replace("'", "")).split()
    out = set()
    for t in toks:
        if t in STOP or YEAR_RX.match(t):
            continue
        out.add(t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith("ss") else t)
    return frozenset(out)


# --------------------------------------------------------------------------- plan rows
class Plan:
    def __init__(self, topic: list[dict], keywords: list[dict] | None, links: list[dict] | None, url_pattern: str,
                 max_secondary: int, volume_mode: str, max_related: int):
        self.url_pattern, self.max_secondary, self.volume_mode, self.max_related = url_pattern, max_secondary, volume_mode, max_related
        self.topic = topic
        self.links = links or []
        self.kw_by_cluster: dict[str, list[dict]] = defaultdict(list)
        for k in keywords or []:
            self.kw_by_cluster[k["cluster_id"]].append(k)
        self.posts = self._order()
        self.stt = {p["planned_slug"]: i for i, p in enumerate(self.posts, 1)}
        self.merged_into: dict[str, list[dict]] = defaultdict(list)
        for r in topic:
            if r["role"] == "merged" and r.get("merged_into"):
                self.merged_into[r["merged_into"]].append(r)

    def _order(self) -> list[dict]:
        posts = [r for r in self.topic if r["role"] in PLANNED and r["planned_slug"]]
        pillars = [r for r in posts if r["role"] == "pillar"]
        pillar_vol = defaultdict(int)
        for r in self.topic:
            if r.get("pillar_id"):
                pillar_vol[r["pillar_id"]] += to_int(r["cluster_volume"], 0)
        pillars.sort(key=lambda r: (-pillar_vol[r["pillar_id"]], r["pillar_id"]))
        by_pillar = defaultdict(list)
        loose = []
        for r in posts:
            if r["role"] == "cluster":
                by_pillar[r["pillar_id"]].append(r)
            elif r["role"] == "standalone":
                if r.get("parent_hint") and any(p["pillar_id"] == r["parent_hint"] for p in pillars):
                    by_pillar[r["parent_hint"]].append(r)
                else:
                    loose.append(r)
        order = []
        for p in pillars:
            order.append(p)
            order += sorted(by_pillar[p["pillar_id"]], key=lambda r: (-to_int(r["priority_score"], 0), -to_int(r["cluster_volume"], 0)))
        return order + sorted(loose, key=lambda r: -to_int(r["cluster_volume"], 0))

    def url(self, slug: str) -> str:
        return self.url_pattern.format(slug=slug)

    def pillar_of(self, post: dict) -> dict | None:
        pid = post["pillar_id"] or post.get("parent_hint", "")
        return next((p for p in self.posts if p["role"] == "pillar" and p["pillar_id"] == pid), None)

    def keywords_of(self, post: dict) -> list[dict]:
        """All keywords of the post: its cluster, then the clusters merged into it."""
        rows = list(self.kw_by_cluster.get(post["cluster_id"], []))
        for m in self.merged_into.get(post["planned_slug"], []):
            rows += self.kw_by_cluster.get(m["cluster_id"], [])
        if not rows:  # no keyword-map: fall back to the keyword lists in topic-map.csv
            names = post["keywords"].split("|") + [k for m in self.merged_into.get(post["planned_slug"], [])
                                                   for k in m["keywords"].split("|")]
            rows = [{"keyword": k, "volume": "", "kd": "", "is_seed": str(int(k == post["primary_keyword"])),
                     "spelling_fixed": "0"} for k in names if k]
        return rows

    def main_metrics(self, post: dict) -> tuple[int | None, int | None]:
        rows = self.kw_by_cluster.get(post["cluster_id"], [])
        main = next((k for k in rows if k["keyword"] == post["primary_keyword"]), None)
        if self.volume_mode == "post":
            vol = to_int(post["cluster_volume"], 0) + sum(to_int(m["cluster_volume"], 0)
                                                          for m in self.merged_into.get(post["planned_slug"], []))
        else:
            vol = to_int(main["volume"]) if main else None
        return vol, (to_int(main["kd"]) if main else None)

    @staticmethod
    def variants_of(k: dict) -> list[dict]:
        """Same-meaning variants merged into a keyword (word order, a year, a fixed typo), with their volumes."""
        names = [v for v in (k.get("variants") or "").split("|") if v]
        vols = (k.get("variant_volumes") or "").split("|")
        return [{"keyword": n, "volume": vols[i] if i < len(vols) else "", "kd": ""} for i, n in enumerate(names)]

    def secondary(self, post: dict) -> tuple[list[str], list[tuple[dict, str]]]:
        seen = {signature(post["primary_keyword"])}
        listed, roles = [], []
        rows = sorted(self.keywords_of(post), key=lambda k: -(to_int(k.get("volume"), 0) or 0))
        for k in rows:
            roles += [(v, "variant") for v in self.variants_of(k)]
            if k["keyword"] == post["primary_keyword"]:
                roles.append((k, "main"))
                continue
            sig = signature(k["keyword"])
            if (len(listed) < self.max_secondary and sig and sig not in seen and k.get("spelling_fixed", "0") != "1"
                    and len(k["keyword"].split()) <= MAX_SECONDARY_WORDS):
                listed.append(k["keyword"])
                seen.add(sig)
                roles.append((k, "secondary"))
            else:
                roles.append((k, "also covers"))
        return listed, roles

    def link_targets(self, post: dict) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        """(internal links, related posts) as (anchor, target slug)."""
        slug = post["planned_slug"]
        mine = [l for l in self.links if l["source_slug"] == slug and l["target_slug"] in self.stt]
        order = {t: i for i, t in enumerate(BODY_LINKS)}
        body = sorted((l for l in mine if l["link_type"] in order), key=lambda l: order[l["link_type"]])
        internal = [(l["anchor"], l["target_slug"]) for l in body]
        related = [(l["anchor"], l["target_slug"]) for l in mine if l["link_type"] == "sibling"][: self.max_related]
        if not self.links:  # no link plan: hub <-> pillar links and the biggest siblings
            pillar = self.pillar_of(post)
            if post["role"] == "pillar":
                internal = [(r["primary_keyword"], r["planned_slug"]) for r in self.posts
                            if r is not post and self.pillar_of(r) is post]
            elif pillar:
                internal = [(pillar["primary_keyword"], pillar["planned_slug"])]
                sibs = [r for r in self.posts if r is not post and r is not pillar and self.pillar_of(r) is pillar]
                related = [(r["primary_keyword"], r["planned_slug"]) for r in sibs[: self.max_related]]
        if post["role"] == "pillar":  # a hub also shows the other hubs of the plan
            others = [p for p in self.posts if p["role"] == "pillar" and p is not post and p["market"] == post["market"]]
            related = [(p["primary_keyword"], p["planned_slug"]) for p in others[: self.max_related]]
        seen, out_internal = set(), []
        for a, t in internal:
            if t not in seen:
                seen.add(t)
                out_internal.append((a, t))
        return out_internal, [(a, t) for a, t in related if t not in seen]

    def rows(self):
        for n, post in enumerate(self.posts, 1):
            pillar = self.pillar_of(post)
            kind = "Pillar" if post["role"] == "pillar" else "Cluster"
            vol, kd = self.main_metrics(post)
            secondary, roles = self.secondary(post)
            internal, related = self.link_targets(post)
            yield {"n": n, "post": post, "kind": kind, "volume": vol, "kd": kd, "secondary": secondary, "roles": roles,
                   "pillar": "" if kind == "Pillar" or not pillar else pillar["primary_keyword"],
                   "internal": internal, "related": related, "url": self.url(post["planned_slug"])}


def link_text(plan: Plan, links: list[tuple[str, str]]) -> str:
    return "\n".join(f"{a} || {plan.url(t)}" for a, t in links)


def link_formula(plan: Plan, links: list[tuple[str, str]], url_col: str, stt_col: str) -> str | None:
    """="anchor || "&IFERROR(INDEX($N:$N,MATCH(7,$A:$A,0)),"")&CHAR(10)&... : reads the target's URL Blog by STT."""
    parts = []
    for a, t in links:
        lit = a.replace('"', '""')
        parts.append(f'"{lit} || "&IFERROR(INDEX(${url_col}:${url_col},MATCH({plan.stt[t]},${stt_col}:${stt_col},0)),"")')
    formula = "&CHAR(10)&".join(parts)
    return formula if formula and len(formula) <= MAX_FORMULA else None


# --------------------------------------------------------------------------- xlsx writer (zip + XML)
def col_letter(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def xml_text(s: str) -> str:
    return escape(ILLEGAL_XML.sub("", str(s)))


STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0"/></numFmts>
<fonts count="2"><font><sz val="11"/><name val="Calibri"/><family val="2"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"><color rgb="FFD9D9D9"/></left><right style="thin"><color rgb="FFD9D9D9"/></right><top style="thin"><color rgb="FFD9D9D9"/></top><bottom style="thin"><color rgb="FFD9D9D9"/></bottom><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="4">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment vertical="top"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def sheet_xml(header: list[str], rows: list[list], widths: list[int], validations: list[tuple[str, list[str]]] = ()) -> str:
    """rows: lists of cells; a cell is str / int / None or ('f', formula, cached_text)."""
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
           '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
           '</sheetView></sheetViews>', '<sheetFormatPr defaultRowHeight="15"/>', "<cols>"]
    out += [f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths)]
    out += ["</cols>", "<sheetData>"]
    for r, cells in enumerate([header] + rows, 1):
        style = 1 if r == 1 else 2
        xs = []
        for c, val in enumerate(cells):
            ref = f"{col_letter(c)}{r}"
            if val is None or val == "":
                if r > 1:
                    xs.append(f'<c r="{ref}" s="2"/>')
                continue
            if isinstance(val, tuple):
                _, formula, cached = val
                xs.append(f'<c r="{ref}" s="2" t="str"><f>{xml_text(formula)}</f><v>{xml_text(cached)}</v></c>')
            elif isinstance(val, int) and r > 1:
                xs.append(f'<c r="{ref}" s="3"><v>{val}</v></c>')
            else:
                xs.append(f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{xml_text(val)}</t></is></c>')
        out.append(f'<row r="{r}">' + "".join(xs) + "</row>")
    out.append("</sheetData>")
    last = f"{col_letter(len(header) - 1)}{len(rows) + 1}"
    out.append(f'<autoFilter ref="A1:{last}"/>')
    if validations and rows:
        out.append(f'<dataValidations count="{len(validations)}">')
        for col, values in validations:
            out.append(f'<dataValidation type="list" allowBlank="1" showErrorMessage="1" sqref="{col}2:{col}{len(rows) + 1}">'
                       f'<formula1>"{xml_text(",".join(values))}"</formula1></dataValidation>')
        out.append("</dataValidations>")
    out.append("</worksheet>")
    return "".join(out)


def write_xlsx(path: str, sheets: list[tuple[str, str]]) -> None:
    names = [n for n, _ in sheets]
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
          + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                    for i in range(1, len(sheets) + 1))
          + '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
          "</Types>")
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            "</Relationships>")
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            "<dc:title>Printerval blog keyword plan</dc:title><dc:creator>printerval-blog-seo</dc:creator>"
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created></cp:coreProperties>')
    workbook = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                + "".join(f'<sheet name="{xml_text(n)}" sheetId="{i}" r:id="rId{i}"/>' for i, n in enumerate(names, 1))
                + '</sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>')
    wb_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                         f'Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1))
               + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
                 'Target="styles.xml"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", ct)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("docProps/core.xml", core)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        zf.writestr("xl/styles.xml", STYLES)
        for i, (_, xml) in enumerate(sheets, 1):
            zf.writestr(f"xl/worksheets/sheet{i}.xml", xml)


# --------------------------------------------------------------------------- main
def build_outputs(plan: Plan, plain_links: bool):
    url_col, stt_col = col_letter(COL["URL Blog"]), col_letter(COL["STT"])
    xlsx_rows, csv_rows, map_rows = [], [], []
    for r in plan.rows():
        cells = [""] * len(COLUMNS)
        cells[COL["STT"]] = r["n"]
        cells[COL["Main Keyword"]] = r["post"]["primary_keyword"]
        cells[COL["Secondary Keyword"]] = "\n".join(r["secondary"])
        cells[COL["Volume"]] = r["volume"] if r["volume"] is not None else ""
        cells[COL["KD"]] = r["kd"] if r["kd"] is not None else ""
        cells[COL["Category Kind"]] = r["kind"]
        cells[COL["Thuộc Pillar"]] = r["pillar"]
        cells[COL["URL Blog"]] = r["url"]
        flat = list(cells)
        for name, links in (("Internal Link (Anchor || URL)", r["internal"]), ("Related Post (Anchor || URL)", r["related"])):
            text = link_text(plan, links)
            flat[COL[name]] = text
            formula = None if plain_links else link_formula(plan, links, url_col, stt_col)
            cells[COL[name]] = ("f", formula, text) if formula else text
        xlsx_rows.append(cells)
        csv_rows.append(flat)
        order = {"main": 0, "secondary": 1, "also covers": 2, "variant": 3}
        for k, role in sorted(r["roles"], key=lambda kr: (order[kr[1]], -(to_int(kr[0].get("volume"), 0) or 0))):
            map_rows.append([r["n"], r["post"]["primary_keyword"], k["keyword"],
                             to_int(k.get("volume")) if to_int(k.get("volume")) is not None else "",
                             to_int(k.get("kd")) if to_int(k.get("kd")) is not None else "", role])
    return xlsx_rows, csv_rows, map_rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--topic-map", required=True, help="topic-map.csv from topic-map")
    ap.add_argument("--keyword-map", help="keyword-map.csv from keyword-clustering (exact volume/KD and every keyword)")
    ap.add_argument("--link-plan", help="link-plan.csv from internal-link-planner")
    ap.add_argument("--out", default="outputs/final-plan.xlsx", help="output .xlsx path (a .csv copy is written next to it)")
    ap.add_argument("--url-pattern", default="https://printerval.com/{slug}",
                    help="planned URL of a post; {slug} is the planned slug (default https://printerval.com/{slug})")
    ap.add_argument("--max-secondary", type=int, default=10, help="secondary keywords per post (default 10)")
    ap.add_argument("--max-related", type=int, default=3, help="related posts per post (default 3)")
    ap.add_argument("--volume", choices=["main", "post"], default="main",
                    help="Volume column: the main keyword's volume (default) or the post's total (an upper bound)")
    ap.add_argument("--market", help="only export posts of this market (us|uk)")
    ap.add_argument("--plain-links", action="store_true", help="write the link columns as text instead of formulas")
    args = ap.parse_args(argv)
    if "{slug}" not in args.url_pattern:
        ap.error("--url-pattern must contain {slug}")

    topic = read_csv(args.topic_map)
    if args.market:
        topic = [r for r in topic if r["market"] == args.market]
    keywords = read_csv(args.keyword_map) if args.keyword_map else None
    links = read_csv(args.link_plan) if args.link_plan else None
    plan = Plan(topic, keywords, links, args.url_pattern, args.max_secondary, args.volume, args.max_related)
    if not plan.posts:
        raise SystemExit("No planned posts (pillar/cluster/standalone) in the topic map.")
    xlsx_rows, csv_rows, map_rows = build_outputs(plan, args.plain_links)

    out = args.out if args.out.lower().endswith(".xlsx") else args.out + ".xlsx"
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    write_xlsx(out, [("Plan", sheet_xml(COLUMNS, xlsx_rows, WIDTHS, [(col_letter(COL["Category Kind"]), ["Pillar", "Cluster"])])),
                     ("Keyword Map", sheet_xml(MAP_COLUMNS, map_rows, MAP_WIDTHS))])
    csv_path = out[:-5] + ".csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:  # BOM: Excel opens the Vietnamese headers correctly
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        w.writerows(csv_rows)
    pillars = sum(1 for r in csv_rows if r[COL["Category Kind"]] == "Pillar")
    print(f"{len(csv_rows)} posts ({pillars} pillars, {len(csv_rows) - pillars} clusters), {len(map_rows):,} keywords placed")
    if not args.keyword_map:
        print("No --keyword-map: Volume/KD are empty and secondary keywords come from topic-map.csv (15 per cluster).", file=sys.stderr)
    if not args.link_plan:
        print("No --link-plan: links are pillar <-> cluster only, with keyword anchors.", file=sys.stderr)
    print(f"Written: {os.path.abspath(out)} and {os.path.abspath(csv_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
