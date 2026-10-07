"""The SEO's grouping is checked and regrouped (--prior-mode audit), keyword difficulty against the site's reach picks
the main keywords and pillars, internal links follow the pillar / sub-hub structure with a budget and a reason, and
the final plan explains it all (sheets SEO Audit and Link Plan)."""
import os
import subprocess
import sys
import tempfile
import unittest

import helpers  # noqa: F401  (sets up sys.path)
from helpers import ROOT, read_csv, run_main, write_text

import cluster_keywords as ck
import kw_kd
import kw_prior
import link_plan as lp
import plan_decisions
import table_io
import topic_map as tm
from test_plan import xlsx_bytes
from test_quality import cl

HEADER = "STT,Main keyword,Secondary keyword,,Volume,KD,Intent,Kind (Pillar/Cluster)\n"
# the SEO's usual sheet: a main row, then its secondary keywords one per row with an empty Main cell
SEO_FILE = HEADER + """53,how to decorate for christmas,,,1300,40,Informational,Pillar
,,how to decor christmas,,260,40,Informational,
,,how to decorate christmas decorations,,260,34,Informational,
54,how to decorate a christmas tree with ribbon,,,1000,55,Informational,Cluster
,,how to decorate christmas tree with ribbon,,590,20,Informational,
,,christmas tree ribbon how to decorate,,900,5,,
,,buy christmas tree ribbon,,320,30,Transactional,
61,how to decorate a christmas tree step by step,,,170,10,Informational,Cluster
,,how to decorate christmas trees,,140,12,Informational,
,,how to decorate your christmas tree,,110,15,Informational,
60,how to decorate a christmas tree professionally,,,170,32,Informational,Cluster
55,how to decorate a christmas tree white,,,390,25,Informational,Cluster
,,how to decorate christmas staircase,,40,,,
67,how to decorate pink christmas tree,,,110,26,Informational,Cluster
58,how to decorate stairs for christmas,,,260,22,Informational,Cluster
,,how to decorate christmas staircase,,40,,,
59,how to decorate for christmas stairs,,,40,,,Cluster
85,how to decorate sparse christmas tree,,,30,,,Cluster
74,how to decorate christmas wreath,,,70,36,Informational,Cluster
183,how to make custom mugs,,,110,45,Informational,
184,how to make custom cups,,,110,27,Informational,Cluster
185,how to make custom tumblers,,,110,17,Informational,Cluster
"""


class GroupedFileLayouts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def path(self, name, content):
        p = os.path.join(self.tmp.name, name)
        if isinstance(content, bytes):
            with open(p, "wb") as fh:
                fh.write(content)
        else:
            write_text(p, content)
        return p

    def test_block_layout_kind_by_order_and_free_rows(self):
        recs, info = kw_prior.read_prior(self.path("seo.csv", HEADER + ",,orphan keyword above,,30,,,\n" + SEO_FILE.split("\n", 1)[1]))
        self.assertEqual(info["layout"], "block")
        by_kw = {r["keyword"]: r for r in recs}
        self.assertIsNone(by_kw["orphan keyword above"]["group_key"])  # above the first group: no group, not dropped
        sec = by_kw["how to decorate christmas trees"]
        self.assertEqual((sec["group"], sec["prior_volume"], sec["prior_kd"], sec["is_main"]), ("61", "140", "12", False))
        self.assertEqual(by_kw["how to decorate a christmas tree step by step"]["pillar"], "how to decorate for christmas")
        # a group with no Kind heads the Cluster rows below it (the SEO's custom mugs block)
        self.assertEqual(by_kw["how to make custom cups"]["pillar"], "how to make custom mugs")
        self.assertEqual(by_kw["how to make custom mugs"]["pillar"], "")
        self.assertEqual(info["block_rows"], 9)

    def test_every_sheet_and_the_plan_secondary_cell_with_a_keyword_map(self):
        plan_header = ["STT", "Main Keyword", "Secondary Keyword", "Volume", "KD", "Category Kind", "Thuộc Pillar"]
        p = self.path("plan.xlsx", xlsx_bytes([
            ("Plan", [plan_header, [1, "christmas gift ideas", "xmas gift ideas\nadded in the plan sheet", 9900, 40, "Pillar"]]),
            ("Keyword Map", [["STT", "Main Keyword", "Keyword", "Volume", "KD", "Role"],
                             [1, "christmas gift ideas", "christmas gift ideas", 9900, 40, "main"],
                             [1, "christmas gift ideas", "xmas gift ideas", 880, 30, "secondary"]]),
            ("Halloween", [["Keyword", "Group", "Volume"], ["halloween costume ideas", "Costumes", 5000],
                           ["costume ideas for halloween", "", 900]]),
            ("Scratch", [["Keyword", "Volume"], ["black friday deals", 100]])]))
        recs, info = kw_prior.read_prior(p)
        kws = {r["keyword"] for r in recs}
        self.assertIn("added in the plan sheet", kws)  # the Plan's own Secondary cell, next to the Keyword Map
        self.assertIn("costume ideas for halloween", kws)  # the second grouped sheet is read too
        self.assertEqual(info["sheets"], ["Plan", "Keyword Map", "Halloween"])
        self.assertIn("Scratch", [s for s, _ in info["sheets_skipped"]])

    def test_keyword_strategy_builder_page_is_the_group(self):
        p = self.path("ksb.csv", "Topic,Page,Keyword,Volume\nchristmas gifts,gifts for mom,christmas gifts for mom,2400\n"
                                 ",,mom christmas presents,300\nchristmas gifts,gifts for dad,christmas gifts for dad,1900\n")
        recs, info = kw_prior.read_prior(p)
        self.assertEqual({r["keyword"]: r["group"] for r in recs},
                         {"christmas gifts for mom": "gifts for mom", "mom christmas presents": "gifts for mom",
                          "christmas gifts for dad": "gifts for dad"})


class KeywordDifficulty(unittest.TestCase):
    def test_fit_labels_and_winnable_volume(self):
        kd = kw_kd.KdModel(30)
        self.assertEqual([kd.label(v) for v in (10, 30, 40, 46, None)], ["easy", "easy", "stretch", "hard", "unknown"])
        self.assertEqual(kd.fit(30), 1.0)
        self.assertAlmostEqual(kd.fit(45), 0.5)
        self.assertEqual(kd.fit(90), kw_kd.FLOOR)
        self.assertEqual(kd.winnable(1000, None), 1000 * kw_kd.UNKNOWN_FIT)
        self.assertEqual(kd.label(45, "semrush:pkd"), "easy")  # a Personal KD is already about this domain

    def test_reach_from_flag_measured_or_default(self):
        self.assertEqual(kw_kd.build_model(42, []).reach, 42)
        ranks = [(3, kd) for kd in range(10, 50, 2)]  # 20 keywords the site ranks top 10 for
        model = kw_kd.build_model(None, ranks + [(25, 90)])  # position 25 does not count
        self.assertEqual(model.reach, 40)
        self.assertIn("measured", model.source)
        self.assertEqual(kw_kd.build_model(None, ranks[:5]).reach, kw_kd.DEFAULT_REACH)

    def test_empty_personal_kd_falls_back_to_keyword_difficulty(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "export.csv")
            write_text(src, "Keyword,Volume,Keyword Difficulty,Personal Keyword Difficulty\n"
                            "christmas gifts for mom,2400,72,\nchristmas gifts for dad,1900,60,35\n")
            assert run_main(ck.main, [src, "--market", "us", "--out", d, "--max-kd", "65"])[0] == 0
            kws = {r["keyword"]: r for r in read_csv(os.path.join(d, "keyword-map.csv"))}
            self.assertNotIn("christmas gifts for mom", kws)  # KD 72 > --max-kd 65: the generic KD was used
            self.assertEqual(kws["christmas gifts for dad"]["kd"], "35")
            self.assertTrue(kws["christmas gifts for dad"]["kd_source"].endswith(":pkd"))


class AuditPipeline(unittest.TestCase):
    """run_plan.py on the SEO's block-layout file: the audit, the topic map, the links and the final sheets."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = cls.dir = cls.tmp.name
        src = os.path.join(d, "seo.csv")
        write_text(src, SEO_FILE)
        script = os.path.join(ROOT, "skills", "printerval-blog-seo", "scripts", "run_plan.py")
        cls.proc = subprocess.run([sys.executable, script, "--prior", src + "::us", "--out", os.path.join(d, "out"),
                                  "--today", "2026-10-07", "--year", "2026"], capture_output=True, text=True)
        o = cls.o = staticmethod(lambda name: os.path.join(d, "out", name))  # noqa: E731
        o = o.__func__
        cls.audit = read_csv(o("seo-audit.csv")) + read_csv(o("seo-audit-topic.csv"))
        cls.topic = {r["primary_keyword"]: r for r in read_csv(o("topic-map.csv"))}
        cls.links = read_csv(o("link-plan.csv"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def find(self, check, keyword=None):
        return [a for a in self.audit if a["check"] == check and (keyword is None or a["keyword"] == keyword)]

    def test_the_pipeline_runs(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)
        self.assertIn("SEO Audit:", self.proc.stdout)

    def test_same_query_in_two_groups_is_one_post(self):
        merged = self.find("same_query", "how to decorate for christmas stairs")
        self.assertEqual(merged[0]["target_main"], "how to decorate stairs for christmas")
        self.assertNotIn("how to decorate for christmas stairs", self.topic)

    def test_a_keyword_listed_twice_stays_where_it_fits(self):
        dup = self.find("duplicate", "how to decorate christmas staircase")
        self.assertEqual((dup[0]["seo_group"], dup[0]["target_main"]),
                         ("55", "how to decorate stairs for christmas"))

    def test_shopping_keyword_split_out(self):
        self.assertTrue(self.find("shop_member", "buy christmas tree ribbon"))
        self.assertEqual(self.topic["buy christmas tree ribbon"]["role"], "skip")

    def test_easier_main_keyword_but_never_an_inverted_one(self):
        change = self.find("main_changed")
        self.assertEqual([a["keyword"] for a in change], ["how to decorate christmas tree with ribbon"])
        self.assertIn("easier to rank", change[0]["evidence"])
        self.assertIn("how to decorate christmas tree with ribbon", self.topic)  # KD 20 beats KD 55 for the title

    def test_small_group_becomes_a_section_of_the_closest_post(self):
        sec = {a["keyword"]: a["target_main"] for a in self.find("section")}
        self.assertEqual(sec["how to decorate sparse christmas tree"], "how to decorate a christmas tree step by step")
        self.assertEqual(sec["how to decorate christmas wreath"], "how to decorate for christmas")
        self.assertEqual(self.topic["how to decorate sparse christmas tree"]["role"], "merged")

    def test_angle_words_aside_two_groups_ask_the_same(self):
        same = self.find("same_subject", "how to decorate a christmas tree professionally")
        self.assertEqual(same[0]["target_main"], "how to decorate a christmas tree step by step")

    def test_sub_hub_between_the_pillar_and_its_tree_posts(self):
        hub = "how-to-decorate-a-christmas-tree-step-by-step"
        self.assertEqual(self.topic["how to decorate a christmas tree white"]["parent_post"], hub)
        self.assertEqual(self.topic["how to decorate pink christmas tree"]["parent_post"], hub)
        self.assertIn("sub-hub", self.topic["how to decorate a christmas tree step by step"]["note"])
        self.assertEqual(self.topic["how to decorate stairs for christmas"]["parent_post"], "")
        types = {(l["source_slug"], l["target_slug"]): l["link_type"] for l in self.links}
        pillar = "how-to-decorate-for-christmas"
        self.assertEqual(types[("how-to-decorate-a-christmas-tree-white", hub)], "to_parent")
        self.assertEqual(types[("how-to-decorate-a-christmas-tree-white", pillar)], "to_pillar")
        self.assertEqual(types[(hub, "how-to-decorate-a-christmas-tree-white")], "from_parent")
        self.assertNotIn((pillar, "how-to-decorate-a-christmas-tree-white"), types)  # reached through the sub-hub
        self.assertEqual(types[(pillar, hub)], "from_pillar")

    def test_every_link_has_a_reason_and_a_placement(self):
        self.assertTrue(all(l["reason"] and l["placement"] for l in self.links))

    def test_the_block_head_with_no_kind_is_its_own_pillar(self):
        self.assertEqual(self.topic["how to make custom mugs"]["role"], "pillar")
        self.assertEqual(self.topic["how to make custom cups"]["pillar_id"], self.topic["how to make custom mugs"]["pillar_id"])

    def test_final_plan_sheets(self):
        plan = self.o("final-plan.xlsx")
        audit = table_io.read_table(plan, {"seo stt"}, sheet="SEO Audit")
        results = {(r["SEO STT"], r["Result"]) for r in audit}
        self.assertIn(("53", "kept as pillar"), results)
        self.assertIn(("85", "section"), results)
        self.assertIn(("59", "merged"), results)
        sec = next(r for r in audit if r["SEO STT"] == "85")
        stt = {r["Main Keyword"]: r["STT"] for r in read_csv(self.o("final-plan.csv"))}
        self.assertEqual(sec["Now in Plan (STT)"], stt["how to decorate a christmas tree step by step"])
        links = table_io.read_table(plan, {"from stt"}, sheet="Link Plan")
        self.assertTrue(links and all(r["Reason"] for r in links))
        self.assertEqual(len(read_csv(self.o("final-plan.csv"))[0]), 15)  # the team's 15 columns are untouched

    def test_keep_mode_keeps_every_group(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "seo.csv")
            write_text(src, SEO_FILE)
            assert run_main(ck.main, ["--prior", src + "::us", "--prior-mode", "keep", "--out", d])[0] == 0
            cls = read_csv(os.path.join(d, "clusters.csv"))
            self.assertEqual(len({c["prior_group"] for c in cls if c["prior_group"]}), 13)
            self.assertFalse(os.path.exists(os.path.join(d, "seo-audit.csv")))


class TopicMapRules(unittest.TestCase):
    def test_theme_hub_names_no_narrower_audience(self):
        xmas = dict(occasion="christmas", theme="gifts")
        rows = [cl("M", "christmas gifts for mom", 9000, "inspire", recipient="mom", **xmas),
                cl("I", "christmas gift ideas", 4000, "inspire", **xmas)]
        self.assertEqual(tm.choose_theme_hub(rows, "occasion")["cluster_id"], "I")

    def test_hub_is_the_one_the_site_can_win(self):
        rows = [cl("A", "thanksgiving activities", 9000, "inspire", cluster_winnable="900"),
                cl("B", "things to do on thanksgiving", 5000, "inspire", cluster_winnable="5000")]
        self.assertEqual(tm.choose_theme_hub(rows)["cluster_id"], "B")

    def test_two_seo_pillars_with_names_that_slugify_alike_stay_apart(self):
        seo = dict(occasion="christmas", grouping_basis="prior:seo")
        rows = [cl("A", "mugs & cups gift ideas", 9000, "inspire", prior_group="1", prior_role="Pillar", **seo),
                cl("A2", "mug gifts for mom", 500, "inspire", prior_group="2", prior_pillar="mugs & cups gift ideas", **seo),
                cl("B", "mugs cups gift ideas", 7000, "inspire", prior_group="3", prior_role="Pillar", **seo),
                cl("B2", "cup gifts for dad", 400, "inspire", prior_group="4", prior_pillar="mugs cups gift ideas", **seo)]
        out, _ = tm.build(rows, ["occasion"], 3, None)
        hubs = [o for o in out if o["role"] == "pillar"]
        self.assertEqual(sorted(o["cluster_id"] for o in hubs), ["A", "B"])
        self.assertEqual(len({o["planned_slug"] for o in out if o["planned_slug"]}), 4)
        self.assertTrue(all(o["pillar_key"].startswith("christmas/") for o in hubs))  # found by its topic

    def test_seo_pillar_gives_way_to_a_broader_group_the_site_can_win(self):
        seo = dict(occasion="christmas", grouping_basis="prior:audited", reader_need="how_to")
        rows = [cl("P", "how to decorate a christmas tree like a pro", 3000, prior_group="1", prior_role="Pillar",
                   core="tree pro", cluster_winnable="300", seed_kd="70", **seo),
                cl("T", "how to decorate a christmas tree", 1500, prior_group="2", core="tree", cluster_winnable="1500",
                   prior_pillar="how to decorate a christmas tree like a pro", **seo)]
        log = []
        out, _ = tm.build(rows, ["occasion"], 3, None, audit_log=log)
        self.assertEqual(next(o for o in out if o["role"] == "pillar")["cluster_id"], "T")
        # 'like a pro' is an angle: the old pillar asks what the new one asks, so it is merged into it
        self.assertEqual([a["check"] for a in log], ["pillar_changed", "same_subject"])

    def test_parent_hint_never_names_a_group_with_no_pillar(self):
        rows = [cl("A", "christmas mugs for mom", 900, "inspire", occasion="christmas", recipient="mom", product="mug"),
                cl("B", "christmas socks for mom", 800, "inspire", occasion="christmas", recipient="mom", product="socks"),
                cl("C", "christmas pajamas for mom", 700, "inspire", occasion="christmas", recipient="mom", product="pajamas"),
                cl("K", "how to wrap a gift for mom", 300, "how_to", recipient="mom")]
        out, _ = tm.build(rows, ["occasion", "recipient"], 3, None, promote_min_share=0.9)
        pids = {o["pillar_id"] for o in out if o["role"] == "pillar"}
        hint = next(o for o in out if o["cluster_id"] == "K")["parent_hint"]
        self.assertTrue(hint == "" or hint in pids)


class LinkRules(unittest.TestCase):
    def post(self, slug, kw, role="cluster", kws=(), **extra):
        r = {"pillar_id": "P01", "pillar_key": "christmas/decor", "role": role, "cluster_id": slug, "primary_keyword": kw,
             "planned_slug": slug, "cluster_volume": "100", "priority_score": "100", "market": "us",
             "keywords": "|".join([kw, *kws]), "post_type": "how-to", "parent_hint": "", "merged_into": "",
             "occasion": "christmas", "parent_post": "", "main_kd_fit": ""}
        r.update(extra)
        return r

    def test_pillar_budget_and_up_links(self):
        rows = [self.post("pillar", "how to decorate for christmas", role="pillar")]
        rows += [self.post(f"p{i}", f"how to decorate christmas thing{i}", priority_score=str(1000 - i)) for i in range(6)]
        pl = lp.Planner(rows, None, 3, 1, pillar_links=4)
        pl.build()
        down = [d for (s, d), l in pl.links.items() if s == "pillar" and l["link_type"] == "from_pillar"]
        self.assertEqual(sorted(down), ["p0", "p1", "p2", "p3"])  # the most valuable posts within the budget
        self.assertTrue(all(("p%d" % i, "pillar") in pl.links for i in range(6)))  # every post links up
        self.assertEqual({s for s, _ in pl.later}, {"p4", "p5"})

    def test_anchors_describe_the_target(self):
        row = self.post("t", "how to decorate a 9 foot christmas tree",
                        kws=("how to decorate a 10ft christmas tree", "christmas tree how to decorate",
                             "how to decorate 9 foot christmas trees", "how to attach decor to a roof"))
        self.assertEqual(lp.anchor_candidates(row), ["how to decorate a 9 foot christmas tree",
                                                    "how to decorate 9 foot christmas trees"])
        dated = self.post("d", "when is thanksgiving 2026 in the united states of america this year")
        self.assertEqual(lp.anchor_candidates(dated), ["when is thanksgiving in the united states of america"])

    def test_one_anchor_text_per_target_and_market(self):
        a = self.post("gifts-for-teachers", "gifts for teachers")
        b = self.post("gifts-for-teachers-uk", "gifts for teachers", market="uk")
        pl = lp.Planner([a, b, self.post("x", "teacher appreciation ideas")], None, 3, 1)
        self.assertEqual(pl.pick_anchor(a)[0], "gifts for teachers")
        self.assertEqual(pl.pick_anchor(b)[0], "gifts for teachers")  # another market: not a clash

    def test_hard_targets_may_receive_more_contextual_links(self):
        rows = [self.post(f"s{i}", f"christmas tree ribbon idea {i}", kws=("christmas tree ribbon",)) for i in range(6)]
        rows.append(self.post("easy", "christmas tree ribbon", main_kd_fit="easy", priority_score="1"))
        rows.append(self.post("hard", "christmas tree ribbon guide", main_kd_fit="hard", priority_score="1"))
        pl = lp.Planner(rows, None, 3, 1, max_contextual=2)
        pl.build()
        self.assertLessEqual(pl.ctx_in["easy"], lp.INBOUND_CONTEXTUAL["easy"])
        self.assertLessEqual(pl.ctx_in["hard"], lp.INBOUND_CONTEXTUAL["hard"])


class DecisionsFiles(unittest.TestCase):
    def test_pipes_in_a_cell_and_a_semicolon_file(self):
        with tempfile.TemporaryDirectory() as d:
            pipes = os.path.join(d, "pipes.csv")
            ids = "|".join(f"BC-{i:08x}" for i in range(40))
            write_text(pipes, "decision_id,action,keyword,value,reason,evidence,source_issue,author\n"
                              f"D-1,set_title,stt:1,A Title,why,proof,{ids},claude\n")
            self.assertEqual(plan_decisions.read_decisions(pipes)[0]["source_issue"], ids)
            semi = os.path.join(d, "semi.csv")
            write_text(semi, "Decision_ID;Action;Keyword;Value;Reason;Evidence\nD-2;set_meta;stt:1;A, B;why;proof\n")
            row = plan_decisions.read_decisions(semi)[0]
            self.assertEqual((row["decision_id"], row["value"], row["reason"]), ("D-2", "A, B", "why"))
            self.assertEqual(tm.read_decisions(semi)[0]["action"], "set_meta")

    def test_markets_read_like_the_cluster_step(self):
        self.assertEqual([plan_decisions.norm_market(m) for m in ("GB", "all", "", "us")], ["uk", "", "", "us"])

    def test_a_proposal_is_never_applied(self):
        dec = ck.ClusterDecisions([{"decision_id": "P-BC-1", "action": "merge", "market": "us", "keyword": "a",
                                    "target": "b", "value": "", "reason": "r", "evidence": "e", "author": "proposal",
                                    "_row": 2}], {})
        self.assertEqual(dec.items[0]["status"], "invalid")
        self.assertIn("proposal", dec.items[0]["detail"])


class SheetMarkets(unittest.TestCase):
    def test_a_sheet_named_after_a_market(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "both.xlsx")
            with open(p, "wb") as fh:
                fh.write(xlsx_bytes([("US", [["Keyword", "Volume"], ["gifts for mom", 9900]]),
                                     ("UK", [["Keyword", "Volume"], ["gifts for mum", 4400]])]))
            assert run_main(ck.main, [p, "--market", "us", "--out", d])[0] == 0
            kws = {r["keyword"]: r["market"] for r in read_csv(os.path.join(d, "keyword-map.csv"))}
            self.assertEqual(kws, {"gifts for mom": "us", "gifts for mum": "uk"})


class ReviewRegressions(unittest.TestCase):
    """Bugs found by the independent review of the audit, each reproduced first."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def cluster(self, body, *extra):
        d = self.tmp.name
        src = os.path.join(d, "seo.csv")
        write_text(src, HEADER + body)
        code, _, err = run_main(ck.main, ["--prior", src + "::us", "--out", d, *extra])
        self.assertEqual(code, 0, err)
        return (read_csv(os.path.join(d, "keyword-map.csv")), read_csv(os.path.join(d, "clusters.csv")),
                read_csv(os.path.join(d, "seo-audit.csv")))

    def topic(self):
        d = self.tmp.name
        self.assertEqual(run_main(tm.main, [os.path.join(d, "clusters.csv"), "--out", d])[0], 0)
        return read_csv(os.path.join(d, "topic-map.csv"))

    def test_a_duplicate_is_folded_not_lost(self):
        kws, _, audit = self.cluster("1,how to decorate stairs for christmas,,,260,22,,Cluster\n"
                                     ",,christmas garland stairs ideas,,170,20,,\n"
                                     "2,how to hang garland on stairs,,,300,22,,Cluster\n"
                                     ",,stairs christmas garland ideas,,150,20,,\n")
        listed = {r["keyword"] for r in kws} | {v for r in kws for v in r["variants"].split("|") if v}
        self.assertTrue({"christmas garland stairs ideas", "stairs christmas garland ideas"} <= listed)
        self.assertEqual([a["check"] for a in audit], ["duplicate"])

    def test_year_rule_only_takes_the_same_query(self):
        _, cls, _ = self.cluster("1,christmas gift ideas 2026,,,1000,30,,Pillar\n,,white elephant gift rules,,210,20,,\n"
                                 ",,christmas gift ideas for mom 2026,,300,20,,\n")
        self.assertEqual(cls[0]["cluster_name"], "christmas gift ideas 2026")  # not 'white elephant gift rules'
        _, cls, audit = self.cluster("1,christmas gift ideas 2026,,,1000,30,,Pillar\n,,christmas gift ideas,,8000,30,,\n")
        self.assertEqual(cls[0]["cluster_name"], "christmas gift ideas")  # the year-free variant folded into the main
        self.assertEqual(audit[0]["check"], "main_changed")

    def test_a_pillar_renamed_by_the_audit_keeps_its_posts(self):
        self.cluster("1,how to decorate a christmas tree with ribbon,,,1000,55,,Pillar\n"
                     ",,how to decorate christmas tree with ribbon,,590,20,,\n"
                     "2,how to decorate a christmas tree white,,,390,25,,Cluster\n"
                     "3,how to decorate pink christmas tree,,,410,26,,Cluster\n"
                     "4,how to decorate a christmas tree step by step,,,370,10,,Cluster\n")
        out = self.topic()
        hub = next(r for r in out if r["role"] == "pillar")
        self.assertEqual(hub["primary_keyword"], "how to decorate christmas tree with ribbon")
        self.assertEqual({r["pillar_id"] for r in out if r["role"] == "cluster"}, {hub["pillar_id"]})

    def test_two_groups_with_the_same_main_are_one_post(self):
        _, cls, audit = self.cluster("1,how to decorate stairs for christmas,,,260,22,,Cluster\n"
                                     ",,how to decorate christmas stairs,,170,20,,\n"
                                     "2,how to decorate stairs for christmas,,,260,22,,Cluster\n"
                                     ",,christmas staircase decor ideas,,150,20,,\n")
        self.assertEqual(len(cls), 1)
        self.assertEqual([a["check"] for a in audit], ["same_query"])

    def test_a_merge_into_a_post_that_became_a_section_follows_it(self):
        self.cluster("1,how to decorate for christmas,,,1300,40,,Pillar\n"
                     "2,how to decorate a christmas tree step by step,,,60,10,,Cluster\n"
                     "3,how to decorate a christmas tree professionally,,,30,32,,Cluster\n"
                     "4,how to decorate stairs for christmas,,,260,22,,Cluster\n"
                     "5,how to decorate christmas mantel,,,460,25,,Cluster\n")
        out = {r["primary_keyword"]: r for r in self.topic()}
        slugs = {r["planned_slug"] for r in out.values() if r["planned_slug"]}
        for kw in ("how to decorate a christmas tree step by step", "how to decorate a christmas tree professionally"):
            self.assertEqual(out[kw]["role"], "merged")
            self.assertIn(out[kw]["merged_into"], slugs)  # never a post that is itself merged away

    def test_a_decision_does_not_switch_the_topic_audit_off(self):
        d = self.tmp.name
        dec = os.path.join(d, "dec.csv")
        write_text(dec, "decision_id,action,market,keyword,target,value,reason,evidence,source_issue,author,date\n"
                        "D-1,move_keyword,us,how to decor christmas,how to decorate christmas wreath,,r,e,,seo,\n")
        _, cls, _ = self.cluster(SEO_FILE.split("\n", 1)[1], "--decisions", dec)
        self.assertEqual({c["seo_audited"] for c in cls if c["prior_group"]}, {"1"})
        self.topic()
        checks = {a["check"] for a in read_csv(os.path.join(d, "seo-audit-topic.csv"))}
        self.assertIn("section", checks)

    def test_the_final_plan_as_prior_reads_plan_and_keyword_map_only(self):
        plan_header = ["STT", "Main Keyword", "Secondary Keyword", "Volume", "KD", "Category Kind", "Thuộc Pillar"]
        p = os.path.join(self.tmp.name, "final-plan.xlsx")
        with open(p, "wb") as fh:
            fh.write(xlsx_bytes([("Plan", [plan_header, [1, "christmas gift ideas", "", 9900, 40, "Pillar"]]),
                                 ("Keyword Map", [["STT", "Main Keyword", "Keyword", "Volume", "KD", "Role"],
                                                  [1, "christmas gift ideas", "christmas gift ideas", 9900, 40, "main"]]),
                                 ("Schedule", [["Order", "STT", "Main Keyword", "Category Kind"],
                                               [1, 1, "christmas gift ideas", "Pillar"]]),
                                 ("Back-check", [["issue_id", "check", "group", "keyword"],
                                                 ["BC-1", "weak_member", "1", "christmas gift ideas"]])]))
        recs, info = kw_prior.read_prior(p)
        self.assertEqual((info["groups"], info["sheets"]), (1, ["Plan", "Keyword Map"]))

    def test_groups_of_two_sheets_never_collide(self):
        p = os.path.join(self.tmp.name, "two.xlsx")
        head = ["STT", "Main Keyword", "Secondary Keyword", "Volume", "KD"]
        with open(p, "wb") as fh:
            fh.write(xlsx_bytes([("Christmas", [head, [1, "christmas gift ideas", "", 9900, 40]]),
                                 ("Halloween", [head, [1, "halloween costume ideas", "", 5000, 30]])]))
        recs, _ = kw_prior.read_prior(p)
        self.assertEqual(sorted(r["group"] for r in recs), ["Christmas: 1", "Halloween: 1"])

    def test_a_uk_keyword_with_the_us_main_text_is_kept(self):
        d = self.tmp.name
        src = os.path.join(d, "usuk.csv")
        write_text(src, "STT,Main keyword,Secondary keyword,Volume,KD,Kind,Market\n"
                        "3,christmas gifts for dad,,4400,35,Cluster,us\n,,christmas gifts for dad,1900,30,,uk\n")
        recs, _ = kw_prior.read_prior(src)
        self.assertEqual(sorted(r["market"] for r in recs), ["uk", "us"])

    def test_decision_values_stay_owned_after_an_already_true_run(self):
        prev = plan_decisions.previous_values([{"Decision ID": "D-1", "Step": "export", "Action": "set_title",
                                                "Keyword": "stt:1", "Value": "Title V1", "Status": "already_true"}])
        self.assertEqual(prev[("D-1", "Title SEO")]["value"], "Title V1")


class LinkRegressions(LinkRules):
    def test_cross_pillar_goes_to_the_biggest_pillar_of_a_topic(self):
        rows = [self.post("p123", "small pillar", role="pillar", pillar_id="P123", pillar_key="cars/seo-a"),
                self.post("p30", "big pillar", role="pillar", pillar_id="P30", pillar_key="cars/seo-b")]
        pl = lp.Planner(rows, None, 3, 1)
        self.assertEqual(pl.pillar_by_key[("us", "cars")], "P30")

    def test_an_orphan_fix_never_breaks_the_pillar_budget(self):
        rows = [self.post("pillar", "how to decorate for christmas", role="pillar")]
        rows += [self.post(f"p{i}", f"how to decorate christmas thing{i}", priority_score=str(1000 - i)) for i in range(6)]
        pl = lp.Planner(rows, None, 3, 1, pillar_links=4)
        pl.build()
        self.assertEqual(sum(1 for (s, _), l in pl.links.items() if s == "pillar" and l["link_type"] != "related_reading"), 4)
        self.assertTrue(all(pl.inbound(f"p{i}") for i in range(6)))  # still reached, from their siblings

    def test_a_relative_clause_is_not_an_inverted_question(self):
        self.assertTrue(lp.describes("gift ideas for dads who love fishing", "gifts for dad who loves fishing"))
        self.assertFalse(lp.describes("christmas how to decorate", "how to decorate for christmas"))


if __name__ == "__main__":
    unittest.main()
