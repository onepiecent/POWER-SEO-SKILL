"""SERP-aware grouping: the modifier rules learnt from the SEO's SERP check (a segment word keeps two groups apart, a
tone word on a list topic merges them), SERP data checked by hand (--serp, serp.csv) that merges or keeps apart, the
topic map that honours 'keep apart', and the final plan's SERP To-do and SERP Check sheets."""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

import helpers  # noqa: F401  (sets up sys.path)
from helpers import ROOT, read_csv, write_text

import kw_audit
import kw_serp
import plan_serp
import table_io
from kw_text import Taxonomy

HEADER = "STT,Main keyword,Secondary keyword,,Volume,KD,Intent,Kind (Pillar/Cluster)\n"
SEO_FILE = HEADER + """1,halloween jokes,,,27100,31,Informational,Pillar
,,funny halloween jokes,,5400,30,Informational,
2,cute halloween jokes,,,260,28,Informational,Cluster
,,cute halloween jokes for kids,,50,,,
10,trio halloween costumes,,,14800,29,Informational,Pillar
,,trio costume ideas,,1000,25,Informational,
11,trio halloween costumes male,,,480,29,Informational,Cluster
12,cute trio halloween costumes,,,590,28,Informational,Cluster
13,easy trio halloween costumes,,,210,22,Informational,Cluster
14,best trio halloween costumes,,,720,27,Informational,Cluster
"""
RUN_PLAN = os.path.join(ROOT, "skills", "printerval-blog-seo", "scripts", "run_plan.py")
JS = os.path.join(ROOT, "skills", "printerval-blog-seo", "assets", "serp-extract.js")


def serp_rows(keyword: str, urls: list[str], market="us", date="2026-10-08") -> str:
    return "".join(f"{keyword}\t{market}\t{i}\t{u}\tT\t{date}\ttest\n" for i, u in enumerate(urls, 1))


def trio_serp() -> str:
    head = [f"https://site{i}.com/trio" for i in range(1, 11)]

    def member(n, slug):
        return head[:n] + [f"https://{slug}{i}.com/x" for i in range(n + 1, 11)]
    return ("keyword\tmarket\tposition\turl\ttitle\tchecked_at\tsource\n" + serp_rows("trio halloween costumes", head)
            + serp_rows("easy trio halloween costumes", member(2, "easy"))
            + serp_rows("best trio halloween costumes", member(5, "best"))
            + serp_rows("cute trio halloween costumes", member(4, "cute")))


def run_plan(d: str, *extra: str) -> tuple[subprocess.CompletedProcess, callable]:
    os.makedirs(d, exist_ok=True)
    src = os.path.join(d, "seo.csv")
    write_text(src, SEO_FILE)
    out = os.path.join(d, "out")
    proc = subprocess.run([sys.executable, RUN_PLAN, "--prior", src + "::us", "--out", out, "--today", "2026-10-08",
                           "--year", "2026", *extra], capture_output=True, text=True)
    return proc, lambda name: os.path.join(out, name)


class ModifierRules(unittest.TestCase):
    def setUp(self):
        tax = Taxonomy.load()
        self.tone, self.lists = tax.tone_words, tax.list_topics

    def kind(self, a, b):
        tax = Taxonomy.load()
        ka, kb = (SimpleNamespace(tokset=frozenset(tax.canon_tokens(x))) for x in (a, b))
        return kw_audit.modifier_kind(ka, kb, self.tone, self.lists)

    def test_a_segment_word_keeps_two_posts(self):
        self.assertEqual(self.kind("trio halloween costumes male", "trio halloween costumes"), ("segment", ["male"]))
        self.assertEqual(self.kind("group costume ideas for 4", "group costume ideas for 5")[0], "segment")
        self.assertEqual(self.kind("last minute diy 80s costume", "last minute diy costume")[0], "segment")

    def test_tone_words_merge_only_on_a_list_topic(self):
        self.assertEqual(self.kind("cute halloween jokes", "halloween jokes"), ("list_tone", ["cute"]))
        self.assertEqual(self.kind("short halloween captions for instagram", "halloween captions for instagram")[0],
                         "list_tone")
        self.assertEqual(self.kind("cute trio halloween costumes", "trio halloween costumes"), ("tone", ["cute"]))
        self.assertEqual(self.kind("cute halloween wishes", "halloween wishes")[0], "tone")  # wishes: 3 of 7 shared

    def test_no_rules_no_kind(self):
        self.assertEqual(kw_audit.modifier_kind(SimpleNamespace(tokset=frozenset("a")),
                                                SimpleNamespace(tokset=frozenset("b")), frozenset(), frozenset()), ("", []))


class SerpFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def path(self, name, text):
        p = os.path.join(self.tmp.name, name)
        write_text(p, text)
        return p

    def test_one_row_per_result(self):
        p = self.path("serp.tsv", "keyword\tmarket\tposition\turl\ttitle\tchecked_at\n"
                                  "Trio Halloween Costumes\tUS\t2\thttps://www.b.com/x/?utm=1\tB, with a comma\t2026-10-01\n"
                                  "trio halloween costumes\tus\t1\thttps://a.com/\tA | site\t2026-10-01\n"
                                  "trio halloween costumes\tus\t3\thttp://b.com/x\tB again\t2026-10-01\n"
                                  "trio halloween costumes\tus\t11\thttps://page-two.com\tP\t2026-10-01\n"
                                  "trio halloween costumes\tgb\t1\thttps://uk.co.uk/\tU\t2026-10-01\n")
        serp, warnings = kw_serp.read_serp([p])
        self.assertEqual(serp[("us", "trio halloween costumes")].urls, ["a.com", "b.com/x"])  # in order, once, page one
        self.assertEqual(serp[("uk", "trio halloween costumes")].urls, ["uk.co.uk"])
        self.assertEqual(warnings, [])
        self.assertEqual(plan_serp.read_serp([p])[("us", "trio halloween costumes")]["urls"], ["a.com", "b.com/x"])

    def test_one_row_per_keyword_the_latest_check_wins_and_no_market(self):
        p = self.path("serp.csv", "keyword,serp_urls,checked_at\n"
                                  "trio halloween costumes,https://old.com|https://old2.com,2026-01-01\n"
                                  "trio halloween costumes,https://new.com https://new2.com,2026-10-01\n")
        serp, warnings = kw_serp.read_serp([p])
        self.assertEqual(serp[("", "trio halloween costumes")].urls, ["new.com", "new2.com"])
        self.assertIn("without a market", warnings[0])
        k = SimpleNamespace(keyword="Trio Halloween Costumes", variants=[], market="uk", urls=frozenset())
        self.assertEqual(kw_serp.apply_serp([k], serp), (1, 0))  # no market: every market
        self.assertEqual(k.urls, {"new.com", "new2.com"})

    def test_a_file_without_the_columns_is_refused(self):
        with self.assertRaises(SystemExit):
            kw_serp.read_serp([self.path("bad.csv", "keyword,volume\nx,10\n")])


class SerpLoop(unittest.TestCase):
    """run_plan.py on a Halloween SEO file: first without SERP data (rules + SERP To-do), then with serp.csv."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.proc, o = run_plan(os.path.join(cls.tmp.name, "a"))
        d = os.path.join(cls.tmp.name, "b")
        os.makedirs(d)
        serp = os.path.join(d, "serp.tsv")
        write_text(serp, trio_serp())
        cls.proc2, o2 = run_plan(d, "--serp", serp)
        cls.o, cls.o2 = staticmethod(o), staticmethod(o2)  # a plain function would become a method

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def audit(self, o, check=None):
        rows = read_csv(o("seo-audit.csv")) + read_csv(o("seo-audit-topic.csv"))
        return [a for a in rows if check is None or a["check"] == check]

    def roles(self, o):
        return {r["primary_keyword"]: r for r in read_csv(o("topic-map.csv"))}

    def test_both_runs_succeed(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)
        self.assertEqual(self.proc2.returncode, 0, self.proc2.stderr)
        self.assertIn("SERP To-do:", self.proc.stdout)
        self.assertIn("SERP data: 4 keyword(s)", self.proc2.stdout)

    def test_rules_without_serp(self):
        tone = self.audit(self.o, "tone_variant")
        self.assertEqual([(a["keyword"], a["target_main"]) for a in tone], [("cute halloween jokes", "halloween jokes")])
        self.assertEqual([a["keyword"] for a in self.audit(self.o, "segment_modifier")], ["trio halloween costumes male"])
        self.assertIn("cute trio halloween costumes", [a["keyword"] for a in self.audit(self.o, "possible_duplicate")])
        roles = self.roles(self.o)
        self.assertNotIn("cute halloween jokes", roles)  # one list answers both
        self.assertEqual(roles["easy trio halloween costumes"]["role"], "merged")  # angle word, no SERP data yet

    def test_serp_todo_asks_only_what_can_change_the_plan(self):
        todo = table_io.read_table(self.o("final-plan.xlsx"), {"keyword"}, sheet="SERP To-do")
        asked = [r["Keyword"] for r in todo]
        self.assertEqual(asked[0], "trio halloween costumes")  # one lookup for every trio pair, asked first
        self.assertTrue({"cute trio halloween costumes", "easy trio halloween costumes",
                         "best trio halloween costumes"} <= set(asked))
        self.assertNotIn("trio halloween costumes male", asked)  # a segment: decided by the rule
        self.assertNotIn("cute halloween jokes", asked)
        self.assertTrue(todo[0]["Google URL"].startswith("https://www.google.com/search?q=trio+halloween+costumes&gl=us"))

    def test_shared_urls_merge_and_too_few_keep_apart(self):
        merged = {a["keyword"]: a for a in self.audit(self.o2, "same_query")}
        self.assertEqual(merged["best trio halloween costumes"]["evidence_type"], "serp")
        self.assertEqual(merged["cute trio halloween costumes"]["target_main"], "trio halloween costumes")
        apart = self.audit(self.o2, "serp_apart")
        self.assertEqual([a["keyword"] for a in apart], ["easy trio halloween costumes"])
        clusters = {c["cluster_name"]: c for c in read_csv(self.o2("clusters.csv"))}
        self.assertEqual(clusters["easy trio halloween costumes"]["keep_apart_from"],
                         clusters["trio halloween costumes"]["cluster_id"])
        roles = self.roles(self.o2)
        self.assertEqual(roles["easy trio halloween costumes"]["role"], "cluster")  # the topic map keeps it apart
        self.assertTrue(self.audit(self.o2, "kept_apart"))

    def test_serp_check_sheet_shows_every_verdict_and_the_plan_follows(self):
        rows = table_io.read_table(self.o2("final-plan.xlsx"), {"keyword a"}, sheet="SERP Check")
        verdict = {(r["Keyword A"], r["Keyword B"]): r for r in rows}
        easy = verdict[("trio halloween costumes", "easy trio halloween costumes")]
        self.assertEqual((easy["Shared Top-10"], easy["Verdict"], easy["Plan Follows"]), ("2/10", "two posts", "yes"))
        self.assertEqual(verdict[("trio halloween costumes", "best trio halloween costumes")]["Plan Follows"], "yes")
        self.assertTrue(all(r["Plan Follows"] == "yes" for r in rows))
        todo = table_io.read_table(self.o2("final-plan.xlsx"), {"keyword"}, sheet="SERP To-do") \
            if "SERP To-do" in self.proc2.stdout else []
        self.assertNotIn("easy trio halloween costumes", [r["Keyword"] for r in todo])  # checked: never asked again


class KeepApartDecision(unittest.TestCase):
    def test_the_topic_map_keeps_a_decided_pair_apart(self):
        with tempfile.TemporaryDirectory() as d:
            dec = os.path.join(d, "decisions.csv")
            write_text(dec, "decision_id,action,market,keyword,target,value,reason,evidence,source_issue,author,date\n"
                            "D-1,keep_apart,us,easy trio halloween costumes,trio halloween costumes,,different SERP,"
                            "2 of 7 shared,,seo,2026-10-08\n"
                            "D-2,merge,us,trio halloween costumes,cute trio halloween costumes,,same SERP,"
                            "5 of 8 shared,,seo,2026-10-08\n")
            proc, o = run_plan(d, "--decisions", dec)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            roles = {r["primary_keyword"]: r for r in read_csv(o("topic-map.csv"))}
            self.assertEqual(roles["easy trio halloween costumes"]["role"], "cluster")
            audit = table_io.read_table(o("final-plan.xlsx"), {"seo stt"}, sheet="SEO Audit")
            cute = next(r for r in audit if r["Keyword"] == "cute trio halloween costumes"
                        and r["Check"] == "possible_duplicate")
            self.assertEqual(cute["Result"], "merged")  # resolved by D-2, no longer 'check SERP'
            self.assertTrue(cute["Why"].startswith("resolved"))


class TodoBudget(unittest.TestCase):
    def test_budget_biggest_decision_first_and_one_lookup_per_keyword(self):
        class Plan:
            stt = {"trio-halloween-costumes": 1}
            posts = [{"planned_slug": "trio-halloween-costumes", "primary_keyword": "trio halloween costumes"}]
        topic = [{"cluster_id": "C1", "role": "pillar", "planned_slug": "trio-halloween-costumes", "cluster_volume": 14800}]
        audits = [{"check": "possible_duplicate", "market": "us", "keyword": k, "keyword_volume": v,
                   "target_main": t} for k, v, t in
                  (("cute trio halloween costumes", 590, "trio halloween costumes"),
                   ("best trio halloween costumes", 720, "trio halloween costumes"),
                   ("tiny trio halloween costumes", 40, "trio halloween costumes"),
                   ("cute duo costumes", 900, "duo costumes"))]  # neither side planned (backlog, --posts): later
        kws = [{"market": "us", "keyword": "trio halloween costumes", "volume": "14800", "cluster_id": "C1"}]
        rows = plan_serp.todo_rows(Plan(), topic, kws, audits, [], {}, budget=2, min_volume=100)
        self.assertEqual([r[2] for r in rows], ["trio halloween costumes", "best trio halloween costumes"])
        rows = plan_serp.todo_rows(Plan(), topic, kws, audits, [], {}, budget=10, min_volume=100)
        self.assertEqual(len(rows), 3)  # 'tiny' (40) is a section whatever the SERP says; 'duo' is not planned
        checked = {("us", "trio halloween costumes"): {"keyword": "trio halloween costumes", "urls": ["a.com"],
                                                       "checked_at": "", "source": ""}}
        rows = plan_serp.todo_rows(Plan(), topic, kws, audits, [], checked, budget=10, min_volume=100)
        self.assertNotIn("trio halloween costumes", [r[2] for r in rows])


class ExtractorScript(unittest.TestCase):
    def test_one_expression_that_works_as_a_bookmarklet(self):
        with open(JS, encoding="utf-8") as fh:
            src = fh.read()
        code = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        self.assertNotRegex(code, r"(^|\s)//", "line comments break a one-line bookmarklet")
        self.assertTrue(code.strip().startswith("(() =>") and code.strip().endswith("})()"))
        for part in ("#search a h3", "'browser'", "gl === 'uk'"):
            self.assertIn(part, code)
        with open(os.path.join(ROOT, "skills", "printerval-blog-seo", "assets", "serp-template.tsv"), encoding="utf-8") as fh:
            header = fh.readline().rstrip("\n").split("\t")
        self.assertEqual(header, ["keyword", "market", "position", "url", "title", "checked_at", "source"])


if __name__ == "__main__":
    unittest.main()
