"""Any topic, any grouped layout, a plan size only on request: groups laid out side by side in columns, the SEO's
groups among export clusters keeping the audit's rules, --posts N, and keyword-tool junk kept out of the secondary
keywords."""
import os
import subprocess
import sys
import tempfile
import unittest

import helpers  # noqa: F401  (sets up sys.path)
from helpers import ROOT, read_csv, write_text

import export_plan
import kw_prior
import topic_map as tm
from test_plan import xlsx_bytes

RUN_PLAN = os.path.join(ROOT, "skills", "printerval-blog-seo", "scripts", "run_plan.py")
# the SEO's scratch sheet: a flat list, then (keyword, volume) pairs side by side, some named in the header row
COLUMNS_SHEET = [
    ["Keyword", "Volume", None, None, "when is black friday", None, None, "black friday shirts", None, None, None],
    ["black friday clothing deals 2025", 390, "black friday deals", 1500000, "when is black friday", 165000, None,
     "black friday shirts", 390, "black friday bags deals", 210],
    ["black friday clothes dryer deals", 320, "black friday ads", 40500, "when is black friday this year", 2400, None,
     "black friday t shirts", 260, "black friday sale bags", 110],
    ["best black friday clothing deals 2025", 170, "black friday sale", 22200, "when is black friday 2026", 720, None,
     "black friday t shirt", 140, "designer bags black friday sale", 110],
    [None, None, None, None, "when does black friday end", 390, None, None, None, None, None],
]


class ColumnGroups(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def path(self, sheets):
        p = os.path.join(self.tmp.name, "grouped.xlsx")
        with open(p, "wb") as fh:
            fh.write(xlsx_bytes(sheets))
        return p

    def test_named_pairs_are_groups_the_rest_is_clustered(self):
        recs, info = kw_prior.read_prior(self.path([("Black Friday", COLUMNS_SHEET)]))
        self.assertEqual(info["layout"], "columns")
        groups = {}
        for r in recs:
            if r["group_key"]:
                groups.setdefault(r["group"], []).append(r)
        self.assertEqual(set(groups), {"when is black friday", "black friday shirts"})
        when = {r["keyword"]: r for r in groups["when is black friday"]}
        self.assertTrue(when["when is black friday"]["is_main"])
        self.assertEqual(when["when does black friday end"]["prior_volume"], "390")
        free = {r["keyword"] for r in recs if not r["group_key"]}
        # the generic 'Keyword' pair and the two unnamed pairs: keywords for the engine, never one post
        self.assertTrue({"black friday clothing deals 2025", "black friday deals", "black friday bags deals"} <= free)

    def test_an_export_sheet_is_not_read_as_column_groups(self):
        export = [["Keyword", "Intent", "Volume", "Keyword Difficulty", "SERP Features", "Number of Results"]]
        export += [[f"black friday deal {i}", "Commercial", 100 + i, 30, "Sitelinks, People also ask", 1000 * i]
                   for i in range(1, 8)]
        with self.assertRaises(SystemExit):  # no grouped layout at all: refused, as before
            kw_prior.read_prior(self.path([("Export", export)]))


class MixedPillar(unittest.TestCase):
    """An SEO group among export clusters keeps the audit's rules (a date question is not a section of 'deals'), and
    an export cluster asking the same question follows it."""

    def test_the_seo_group_stays_a_post_and_its_question_joins_it(self):
        with tempfile.TemporaryDirectory() as d:
            grouped = os.path.join(d, "grouped.xlsx")
            with open(grouped, "wb") as fh:
                fh.write(xlsx_bytes([("BF", COLUMNS_SHEET)]))
            export = os.path.join(d, "export.csv")
            rows = ["keyword,volume,kd", "black friday date,14800,20", "what day is black friday,6600,22",
                    "black friday streaming deals,8100,30", "best black friday deals,135000,70"]
            rows += [f"black friday {w} deals,{300 + i * 10},25" for i, w in enumerate(
                ["laptop", "tv", "shoe", "toy", "watch", "phone", "game", "camera", "tablet", "kitchen", "jewelry",
                 "furniture", "mattress", "headphone"])]
            write_text(export, "\n".join(rows) + "\n")
            out = os.path.join(d, "out")
            proc = subprocess.run([sys.executable, RUN_PLAN, export + "::us", "--prior", grouped + "::us", "--out", out,
                                   "--today", "2026-10-08"], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            roles = {r["primary_keyword"]: r for r in read_csv(os.path.join(out, "topic-map.csv"))}
            self.assertIn(roles["when is black friday"]["role"], ("cluster", "pillar"))  # not a section of 'deals'
            kmap = {r["keyword"]: r["cluster_id"] for r in read_csv(os.path.join(out, "keyword-map.csv"))}
            for kw in ("black friday date", "what day is black friday"):  # the same question: one post, not two
                self.assertEqual(kmap[kw], kmap["when is black friday"], kw)
            joined = [a for a in read_csv(os.path.join(out, "seo-audit.csv")) if a["check"] == "same_question"]
            self.assertEqual({a["keyword"] for a in joined}, {"black friday date"})
            self.assertNotIn("black friday streaming deals",
                             [k for k, c in kmap.items() if c == kmap["when is black friday"]])


class PlanSize(unittest.TestCase):
    def rows(self):
        def post(slug, role, score, pid="P1", merged_into=""):
            return {"pillar_id": pid, "role": role, "planned_slug": slug if role != "merged" else "",
                    "primary_keyword": slug.replace("-", " "), "priority_score": score, "merged_into": merged_into,
                    "post_type": role, "bucket": "", "parent_post": "", "note": ""}
        return [post("hub", "pillar", 10), post("big", "cluster", 900), post("mid", "cluster", 500),
                post("small", "cluster", 50), post("sec", "merged", 0, merged_into="small"),
                post("other-hub", "pillar", 400, pid="P2"), post("other", "cluster", 450, pid="P2")]

    def test_no_request_no_cap(self):
        out = self.rows()
        self.assertEqual(tm.limit_posts(out, 0), 0)
        self.assertEqual(sum(o["role"] != "merged" for o in out), 6)

    def test_the_best_posts_with_their_pillar_and_the_rest_in_the_backlog(self):
        out = self.rows()
        self.assertEqual(tm.limit_posts(out, 4), 2)
        planned = {o["planned_slug"] for o in out if o["role"] in tm.PLANNED_ROLES}
        # by priority: big (+ its pillar 'hub', even with a low score), mid, then 'other' needs its pillar too: no room
        self.assertEqual(planned, {"hub", "big", "mid", "other-hub"})
        small = next(o for o in out if o["primary_keyword"] == "small")
        self.assertEqual(small["role"], "backlog")
        self.assertIn("beyond --posts 4", small["note"])
        sec = next(o for o in out if o["primary_keyword"] == "sec")
        self.assertEqual((sec["role"], sec["merged_into"]), ("backlog", ""))  # a section follows its post
        self.assertTrue(all(o["bucket"] for o in out if o["role"] in tm.PLANNED_ROLES))

    def test_run_plan_posts(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "out")
            src = [os.path.join(ROOT, "examples", f"synthetic-keywords-{m}.csv") + f"::{m}" for m in ("us", "uk")]
            proc = subprocess.run([sys.executable, RUN_PLAN, *src, "--out", out, "--today", "2026-10-08",
                                   "--posts", "12"], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(len(read_csv(os.path.join(out, "final-plan.csv"))), 12)
            self.assertIn("--posts 12", proc.stdout)


class SecondaryKeywords(unittest.TestCase):
    def test_a_stray_letter_is_never_a_secondary_keyword(self):
        rx = export_plan.STRAY_LETTER_RX
        for junk in ("r black friday", "black friday y", "y is black friday called black friday"):
            self.assertRegex(junk, rx)
        for real in ("t shirts black friday sale", "a halloween costume", "v neck shirt", "x mas gifts",
                     "halloween costume ideas for 4"):
            self.assertNotRegex(real, rx)


if __name__ == "__main__":
    unittest.main()
