"""One-topic exports (a Semrush 'thanksgiving' file), .xlsx input, spelling fixes, themes, post consolidation,
theme pillars and the final plan export."""
import csv
import os
import re
import tempfile
import unittest
import zipfile

import helpers  # noqa: F401  (sets up sys.path)
from helpers import read_csv, run_main

import cluster_keywords as ck
import export_plan as ep
import kw_ingest as ing
import kw_text
import link_plan as lp
import topic_map as tm
from kw_text import Respeller, Taxonomy

# A small one-occasion export: the same questions asked in many ways, typos, noise, several sub-topics.
THANKSGIVING = """Keyword,Volume,Keyword Difficulty
when is thanksgiving 2026,90000,40
when is thanksgiving,80000,66
what day is thanksgiving,40000,60
thanksgiving 2026 date,30000,35
what day is thanksgiving 2027,20000,30
when's thanksgiving,9000,50
thanksgivng day,40,70
thanks giving day,300,70
is thanksgiving always on a thursday,3000,35
why is thanksgiving on a thursday,2000,30
which thursday is thanksgiving,900,20
is thanksgiving a federal holiday,3600,72
is thanksgiving a national holiday,1000,60
thanksgiving week,2900,46
thanksgiving weekend,1000,40
history of thanksgiving,6600,66
thanksgiving history,3600,60
how did thanksgiving start,2400,63
origin of thanksgiving,1900,64
when was the first thanksgiving,8100,61
first thanksgiving,6600,60
where was the first thanksgiving,1900,55
who was at the first thanksgiving,800,50
real story of thanksgiving,1600,53
the true story of thanksgiving,900,50
when did thanksgiving become a national holiday,1600,58
which president made thanksgiving a national holiday,1300,55
what is thanksgiving,12100,49
thanksgiving meaning,2000,45
why do we celebrate thanksgiving,9900,50
true meaning of thanksgiving,590,53
thanksgiving trivia,8100,23
thanksgiving trivia questions and answers,2400,25
thanksgiving facts,1900,58
fun facts about thanksgiving,1300,50
thanksgiving jeopardy,700,12
thanksgiving quotes,14800,30
thanksgiving prayer,9900,25
thanksgiving bible verses,4400,20
thanksgiving captions,2900,15
funny thanksgiving quotes,1600,20
thanksgiving activities,5400,30
thanksgiving games,9900,35
thanksgiving traditions,2900,21
things to do on thanksgiving,1300,25
thanksgiving games for adults,1000,30
cuando es thanksgiving,6600,50
thanksgiving en,33100,80
trump thanksgiving,1300,40
is walmart open on thanksgiving,5000,40
what restaurants are open on thanksgiving,4000,40
""" + "".join(f"thanksgiving long tail {w},{v},10\n" for w, v in
              [("alpha", 30), ("bravo", 20), ("charlie", 20), ("delta", 10), ("echo", 10), ("foxtrot", 10),
               ("golf", 10), ("hotel", 10), ("india", 10), ("juliet", 10), ("kilo", 10), ("lima", 10), ("mike", 10),
               ("november", 10), ("oscar", 10), ("papa", 10), ("quebec", 10), ("romeo", 10), ("sierra", 10)])


def xlsx_bytes(sheets):
    """A minimal workbook written by hand with shared strings, as Excel/Semrush do: [(name, rows)]."""
    shared, index = [], {}

    def sid(s):
        if s not in index:
            index[s] = len(shared)
            shared.append(s)
        return index[s]

    def col(i):
        return chr(65 + i)

    sheet_xml = []
    for _, rows in sheets:
        xs = []
        for r, cells in enumerate(rows, 1):
            cs = []
            for c, v in enumerate(cells):
                if v is None:
                    continue  # a gap: the reader must keep the columns aligned
                if isinstance(v, (int, float)):
                    cs.append(f'<c r="{col(c)}{r}"><v>{v}</v></c>')
                elif v.startswith("inline:"):
                    cs.append(f'<c r="{col(c)}{r}" t="inlineStr"><is><t>{v[7:]}</t></is></c>')
                else:
                    cs.append(f'<c r="{col(c)}{r}" t="s"><v>{sid(v)}</v></c>')
            xs.append(f'<row r="{r}">{"".join(cs)}</row>')
        sheet_xml.append('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                         + "".join(xs) + "</sheetData></worksheet>")
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("xl/workbook.xml",
                    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                    + "".join(f'<sheet name="{n}" sheetId="{i}" r:id="rId{i}"/>' for i, (n, _) in enumerate(sheets, 1))
                    + "</sheets></workbook>")
        zf.writestr("xl/_rels/workbook.xml.rels",
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    + "".join(f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml" Type="worksheet"/>'
                              for i in range(1, len(sheets) + 1)) + "</Relationships>")
        zf.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    + "".join(f"<si><t>{s}</t></si>" for s in shared) + "</sst>")
        for i, xml in enumerate(sheet_xml, 1):
            zf.writestr(f"xl/worksheets/sheet{i}.xml", xml)
    return buf.getvalue()


class XlsxInput(unittest.TestCase):
    def test_reads_the_sheet_with_a_keyword_column(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "thanksgiving-day_all-keywords_us.xlsx")
            data = xlsx_bytes([
                ("Read me", [["Exported from a keyword tool"], ["nothing else here"]]),
                ("thanksgiving day", [["Semrush export"], ["Keyword", "Intent", "Volume", "Keyword Difficulty"],
                                      ["when is thanksgiving", "Informational", 823000, 66],
                                      ["inline:thanksgiving trivia", None, 8100, 23],
                                      ["thanksgiving 2026", "Informational", 135000, None]])])
            with open(p, "wb") as fh:
                fh.write(data)
            t = ing.read_keywords(p)
            rows = list(t)
            self.assertEqual((t.info["encoding"], t.info["delimiter"], t.info["header_row"]), ("xlsx", "sheet 'thanksgiving day'", 2))
            self.assertEqual(rows[0], {"keyword": "when is thanksgiving", "intent": "Informational", "volume": "823000", "kd": "66"})
            self.assertEqual((rows[1]["keyword"], rows[1]["intent"], rows[1]["volume"]), ("thanksgiving trivia", "", "8100"))
            self.assertEqual(rows[2]["kd"], "")

    def test_no_keyword_sheet_is_a_clear_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.xlsx")
            with open(p, "wb") as fh:
                fh.write(xlsx_bytes([("Sheet1", [["a", "b"], ["c", "d"]])]))
            with self.assertRaises(SystemExit) as cm:
                ing.read_keywords(p)
            self.assertIn("keyword", str(cm.exception))


class Spelling(unittest.TestCase):
    def test_normalisation(self):
        n = kw_text.normalize_text
        self.assertEqual(n("When's Thanksgiving?"), "when is thanksgiving")
        self.assertEqual(n("whats thanksgiving"), "what is thanksgiving")
        self.assertEqual(n("thanksgiving thanksgiving thanksgiving"), "thanksgiving")
        self.assertEqual(n("labor day labor day labor day"), "labor day")
        self.assertEqual(n("thanksgiving.2025"), "thanksgiving 2025")
        self.assertEqual(n("1.5 inch"), "1.5 inch")

    def test_learns_typos_and_split_words_from_the_file(self):
        docs = [["thanksgiving", "day", str(i)] for i in range(60)] + [["thanksgivng", "day"], ["thankgiving"],
                                                                     ["thanks", "giving", "day"], ["celebrates", "it"]]
        docs += [["celebrate", "x", str(i)] for i in range(40)]
        r = Respeller.learn(docs)
        self.assertEqual(r.apply("thanksgivng day"), "thanksgiving day")
        self.assertEqual(r.apply("thankgiving"), "thanksgiving")
        self.assertEqual(r.apply("thanks giving day"), "thanksgiving day")
        self.assertEqual(r.apply("celebrates it"), "celebrates it")  # a word form, not a typo
        self.assertEqual(Respeller.learn(docs[:5]).typos, {})  # too few keywords: nothing is frequent enough

    def test_osa_distance(self):
        self.assertEqual(kw_text.osa_distance("thanksgivign", "thanksgiving"), 1)
        self.assertEqual(kw_text.osa_distance("thansgving", "thanksgiving"), 2)
        self.assertGreater(kw_text.osa_distance("living", "thanksgiving", 2), 2)


class Themes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tax = Taxonomy.load()

    def facets(self, kw):
        return self.tax.detect_facets(kw_text.normalize_text(kw))

    def test_theme_detection(self):
        cases = {"when is thanksgiving": "dates", "thanksgiving 2026": "dates", "thanksgiving": "dates",
                 "is thanksgiving always on a thursday": "dates", "when was the first thanksgiving": "history",
                 "real story of thanksgiving": "history", "true meaning of thanksgiving": "meaning",
                 "what is thanksgiving": "meaning", "why do we celebrate thanksgiving": "meaning",
                 "thanksgiving trivia": "facts", "thanksgiving prayer": "messages", "thanksgiving quotes": "messages",
                 "thanksgiving games": "activities", "thanksgiving traditions": "activities",
                 "why do we eat turkey on thanksgiving": "food", "is thanksgiving celebrated in canada": "world",
                 "who celebrates thanksgiving": "world", "thanksgiving gifts for hostess": "gifts",
                 "mother's day gift ideas": "gifts", "how to wash a graphic tee": ""}
        for kw, want in cases.items():
            self.assertEqual(self.facets(kw)["theme"], want, kw)

    def test_craft_needs_a_product_context(self):
        self.assertEqual(self.facets("what size turkey for 10 people")["craft"], "")
        self.assertEqual(self.facets("t-shirt size chart men")["craft"], "sizing")
        self.assertEqual(self.facets("who designated thanksgiving")["craft"], "")
        self.assertEqual(self.facets("george washington thanksgiving proclamation")["theme"], "history")

    def test_core_tokens(self):
        def core(kw):
            n = kw_text.normalize_text(kw)
            return self.tax.core_tokens(n, self.tax.detect_facets(n)["theme"])
        for kw in ("when is thanksgiving", "what day is thanksgiving 2026", "thanksgiving 2026 date", "when's thanksgiving"):
            self.assertEqual(core(kw), frozenset(), kw)
        self.assertEqual(core("is thanksgiving always on a thursday"), frozenset({"thursday"}))
        self.assertEqual(core("why is thanksgiving on a thursday"), frozenset({"thursday"}))
        self.assertEqual(core("history of thanksgiving"), frozenset())
        self.assertEqual(core("how did thanksgiving start"), frozenset())
        self.assertEqual(core("the true story of thanksgiving"), frozenset({"real"}))

    def test_reader_need_follows_the_theme(self):
        for kw, want in {"thanksgiving 2026": "info", "first thanksgiving": "info", "thanksgiving prayer": "copy_ideas",
                         "thanksgiving trivia": "inspire", "which thursday is thanksgiving": "info",
                         "george washington thanksgiving proclamation": "info"}.items():
            n = kw_text.normalize_text(kw)
            self.assertEqual(self.tax.classify_need(n, self.tax.detect_facets(n)), want, kw)


class OneTopicExport(unittest.TestCase):
    """End to end on a one-occasion export: cluster -> topic map -> link plan -> final plan."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = cls.tmp.name
        cls.src = os.path.join(cls.dir, "thanksgiving.csv")
        with open(cls.src, "w", encoding="utf-8") as fh:
            fh.write(THANKSGIVING)
        assert run_main(ck.main, [cls.src, "--market", "us", "--out", cls.dir, "--only", "occasion=thanksgiving"])[0] == 0
        cls.clusters = read_csv(os.path.join(cls.dir, "clusters.csv"))
        cls.kwmap = read_csv(os.path.join(cls.dir, "keyword-map.csv"))
        assert run_main(tm.main, [os.path.join(cls.dir, "clusters.csv"), "--out", cls.dir, "--max-pillar-size", "8",
                                  "--max-posts", "4", "--target-posts", "0"])[0] == 0
        cls.topic = read_csv(os.path.join(cls.dir, "topic-map.csv"))
        assert run_main(lp.main, ["plan", os.path.join(cls.dir, "topic-map.csv"), "--out", cls.dir])[0] == 0
        cls.xlsx = os.path.join(cls.dir, "final-plan.xlsx")
        assert run_main(ep.main, ["--topic-map", os.path.join(cls.dir, "topic-map.csv"), "--keyword-map",
                                  os.path.join(cls.dir, "keyword-map.csv"), "--link-plan",
                                  os.path.join(cls.dir, "link-plan.csv"), "--out", cls.xlsx])[0] == 0
        with open(cls.xlsx[:-5] + ".csv", encoding="utf-8-sig", newline="") as fh:
            cls.plan = list(csv.DictReader(fh))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def cluster_of(self, keyword):
        cid = next(r["cluster_id"] for r in self.kwmap if r["keyword"] == keyword or keyword in r["variants"].split("|"))
        return next(c for c in self.clusters if c["cluster_id"] == cid)

    # clustering
    def test_noise_rules(self):
        reasons = {r["keyword"]: r["reason"] for r in read_csv(os.path.join(self.dir, "excluded.csv"))}
        self.assertEqual(reasons["cuando es thanksgiving"], "spanish_language")
        self.assertEqual(reasons["thanksgiving en"], "spanish_language")
        self.assertEqual(reasons["trump thanksgiving"], "politics_news")
        self.assertIn(reasons["is walmart open on thanksgiving"], ("retailer_brand_navigational", "opening_hours"))
        self.assertEqual(reasons["what restaurants are open on thanksgiving"], "opening_hours")

    def test_typos_are_kept_and_merged(self):
        fixed = {r["keyword"]: r for r in self.kwmap if r["spelling_fixed"] == "1"}
        self.assertIn("thanks giving day", fixed)
        # 'thanksgivng day' survived --only occasion=thanksgiving thanks to the spelling fix, then became a variant
        self.assertIn("thanksgivng day", fixed["thanks giving day"]["variants"].split("|"))
        hub = next(r for r in self.kwmap if r["keyword"] == "when is thanksgiving")
        self.assertIn("when is thanksgiving 2026", hub["variants"].split("|"))  # the evergreen form names the pair
        self.assertIn("90000", hub["variant_volumes"].split("|"))

    def test_question_variants_become_one_post(self):
        hub = self.cluster_of("when is thanksgiving")
        self.assertEqual(hub["cluster_name"], "when is thanksgiving")  # evergreen name, not 'when is thanksgiving 2026'
        for kw in ("what day is thanksgiving", "thanksgiving 2026 date", "when's thanksgiving", "when is thanksgiving 2026"):
            self.assertEqual(self.cluster_of(kw)["cluster_id"], hub["cluster_id"], kw)
        thursday = self.cluster_of("is thanksgiving always on a thursday")
        self.assertNotEqual(thursday["cluster_id"], hub["cluster_id"])
        self.assertEqual(self.cluster_of("why is thanksgiving on a thursday")["cluster_id"], thursday["cluster_id"])
        self.assertEqual(self.cluster_of("history of thanksgiving")["cluster_id"], self.cluster_of("how did thanksgiving start")["cluster_id"])
        self.assertNotEqual(self.cluster_of("first thanksgiving")["cluster_id"], self.cluster_of("history of thanksgiving")["cluster_id"])

    # topic map
    def test_big_topic_is_split_into_theme_pillars(self):
        pillars = {r["pillar_name"]: r for r in self.topic if r["role"] == "pillar"}
        self.assertIn("Thanksgiving Dates & Calendar", pillars)
        self.assertIn("Thanksgiving History & Origins", pillars)
        self.assertGreaterEqual(len(pillars), 4)
        self.assertEqual(pillars["Thanksgiving Dates & Calendar"]["primary_keyword"], "when is thanksgiving")
        self.assertEqual(pillars["Thanksgiving History & Origins"]["primary_keyword"], "history of thanksgiving")

    def test_caps_merge_and_backlog(self):
        slugs = {r["planned_slug"] for r in self.topic if r["role"] in ("pillar", "cluster", "standalone")}
        self.assertEqual(len(slugs), sum(1 for r in self.topic if r["role"] in ("pillar", "cluster", "standalone")))
        self.assertTrue(all(not re.search(r"(19|20)\d\d", s) for s in slugs))
        merged = [r for r in self.topic if r["role"] == "merged"]
        self.assertTrue(merged)
        self.assertTrue(all(r["merged_into"] in slugs and not r["planned_slug"] for r in merged))
        for pid in {r["pillar_id"] for r in self.topic if r["pillar_id"]}:
            posts = [r for r in self.topic if r["pillar_id"] == pid and r["role"] in ("pillar", "cluster")]
            self.assertLessEqual(len(posts), 4, pid)
        backlog = {r["primary_keyword"] for r in self.topic if r["role"] == "backlog"}
        self.assertIn("thanksgiving jeopardy", backlog)  # a theme too small for a pillar, with no fallback pillar
        # long tail without a theme joins the pillar of a cluster that asks the same thing ('long tail november')
        alpha = next(r for r in self.topic if r["primary_keyword"] == "thanksgiving long tail alpha")
        self.assertEqual((alpha["role"], alpha["pillar_name"]), ("merged", "Thanksgiving Dates & Calendar"))

    def test_links_skip_merged_rows(self):
        links = read_csv(os.path.join(self.dir, "link-plan.csv"))
        slugs = {r["planned_slug"] for r in self.topic if r["planned_slug"]}
        self.assertTrue(links)
        self.assertTrue(all(l["source_slug"] in slugs and l["target_slug"] in slugs for l in links))
        self.assertFalse(any(re.search(r"(19|20)\d\d", l["anchor"]) for l in links))

    # final plan
    def test_plan_columns_and_kinds(self):
        self.assertEqual(list(self.plan[0].keys()), ep.COLUMNS)
        mains = {r["Main Keyword"] for r in self.plan if r["Category Kind"] == "Pillar"}
        self.assertTrue(mains)
        for r in self.plan:
            self.assertIn(r["Category Kind"], ("Pillar", "Cluster"))
            for col in ("Category", "Title SEO", "Meta Description SEO", "Outline", "Trạng thái"):
                self.assertEqual(r[col], "", col)
            if r["Category Kind"] == "Cluster":
                self.assertIn(r["Thuộc Pillar"], mains)
            else:
                self.assertEqual(r["Thuộc Pillar"], "")
            self.assertTrue(r["URL Blog"].startswith("https://printerval.com/"))
        self.assertEqual([int(r["STT"]) for r in self.plan], list(range(1, len(self.plan) + 1)))

    def test_plan_values(self):
        row = next(r for r in self.plan if r["Main Keyword"] == "when is thanksgiving")
        self.assertEqual((row["Volume"], row["KD"], row["Category Kind"]), ("80000", "66", "Pillar"))
        secondary = row["Secondary Keyword"].split("\n")
        self.assertIn("what day is thanksgiving", secondary)
        self.assertNotIn("thanksgivng day", secondary)  # fixed typos stay in the Keyword Map only
        self.assertLessEqual(len(secondary), 10)
        for r in self.plan:
            for col in ("Internal Link (Anchor || URL)", "Related Post (Anchor || URL)"):
                for line in filter(None, r[col].split("\n")):
                    self.assertRegex(line, r"^\S.* \|\| https://printerval\.com/[a-z0-9-]+$")
        thursday = next(r for r in self.plan if r["Main Keyword"] == "is thanksgiving always on a thursday")
        self.assertIn("|| https://printerval.com/when-is-thanksgiving", thursday["Internal Link (Anchor || URL)"])

    def test_xlsx_is_valid_with_formulas_and_keyword_map(self):
        with zipfile.ZipFile(self.xlsx) as zf:
            names = set(zf.namelist())
            self.assertTrue({"[Content_Types].xml", "xl/workbook.xml", "xl/styles.xml", "xl/worksheets/sheet1.xml",
                             "xl/worksheets/sheet2.xml"} <= names)
            sheet = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn("<f>", sheet)
        self.assertIn("MATCH(", sheet)
        self.assertIn('<pane ySplit="1"', sheet)
        name, header_idx, rows = ing._read_xlsx(self.xlsx, {"main keyword"})  # our own reader understands our writer
        self.assertEqual((name, rows[header_idx]), ("Plan", ep.COLUMNS))
        self.assertEqual(len(rows) - 1, len(self.plan))
        with zipfile.ZipFile(self.xlsx) as zf:
            shared = ing._xlsx_shared_strings(zf)
            keyword_map = list(ing._xlsx_rows(zf, "xl/worksheets/sheet2.xml", shared))
        self.assertEqual(keyword_map[0], ep.MAP_COLUMNS)
        placed = {r[2] for r in keyword_map[1:]}
        self.assertIn("thanksgivng day", placed)
        self.assertIn("when is thanksgiving 2026", placed)

    def test_plain_links_and_post_volume(self):
        out = os.path.join(self.dir, "plain.xlsx")
        code, _, err = run_main(ep.main, ["--topic-map", os.path.join(self.dir, "topic-map.csv"), "--keyword-map",
                                          os.path.join(self.dir, "keyword-map.csv"), "--out", out, "--plain-links",
                                          "--volume", "post", "--url-pattern", "https://example.com/blog/{slug}"])
        self.assertEqual(code, 0, err)
        with zipfile.ZipFile(out) as zf:
            self.assertNotIn("<f>", zf.read("xl/worksheets/sheet1.xml").decode("utf-8"))
        rows = read_csv(out[:-5] + ".csv")
        hub = next(r for r in rows if r["Main Keyword"] == "when is thanksgiving")
        self.assertGreater(int(hub["Volume"]), 80000)
        self.assertTrue(hub["URL Blog"].startswith("https://example.com/blog/"))
        self.assertIn("No --link-plan", err)


if __name__ == "__main__":
    unittest.main()
