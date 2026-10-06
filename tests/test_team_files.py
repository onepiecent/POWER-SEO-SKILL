"""The content team's own files: the list of published posts (--published), a previous plan they already work in
(--previous), and the one-command pipeline (run_plan.py)."""
import csv
import os
import re
import subprocess
import sys
import tempfile
import unittest

import helpers  # noqa: F401  (sets up sys.path)
from helpers import ROOT, read_csv, run_main

import cluster_keywords as ck
import export_plan as ep
import link_plan as lp
import table_io
import topic_map as tm
from published import Published, anchor_from_title
from test_plan import THANKSGIVING, xlsx_bytes

PUBLISHED = [
    {"URL": "https://printerval.com/when-is-thanksgiving-this-year-n657.html",
     "Title": "When Is Thanksgiving In 2024? The wonderful facts you should know about this day!", "Category": "Lifestyle"},
    {"URL": "https://printerval.com/when-did-thanksgiving-day-begin-n312.html", "Title": "When Did Thanksgiving Day Begin?",
     "Category": "Lifestyle"},
    {"URL": "https://printerval.com/thanksgiving-games-for-family-shirts-n900001.html",
     "Title": "Top 20 Thanksgiving Games Shirts for Family to Wear All Day", "Category": "Gift Ideas"},
    {"URL": "https://printerval.com/snoopy-thanksgiving-games-n900002.html", "Title": "Top 10 Snoopy Thanksgiving Games Mugs",
     "Category": "Gift Ideas"},
    {"URL": "https://printerval.com/thanksgiving-gift-for-girlfriend-n907350.html", "Title": "Thanksgiving Gifts For Girlfriend",
     "Category": "Gift Ideas"},
    {"URL": "https://printerval.com/thanksgiving-gift-for-girlfriend-n907340.html", "Title": "50+ Thanksgiving Gifts For Girlfriend",
     "Category": "Gift Ideas"},
]


class OneTopicPlanFiles(unittest.TestCase):
    """A plan built from the fixture export, then exported with the team's files."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = cls.dir = cls.tmp.name
        src = os.path.join(d, "thanksgiving.csv")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(THANKSGIVING)
        assert run_main(ck.main, [src, "--market", "us", "--out", d, "--only", "occasion=thanksgiving"])[0] == 0
        assert run_main(tm.main, [os.path.join(d, "clusters.csv"), "--out", d, "--max-pillar-size", "8", "--max-posts", "4"])[0] == 0
        assert run_main(lp.main, ["plan", os.path.join(d, "topic-map.csv"), "--out", d])[0] == 0
        cls.published = os.path.join(d, "published.xlsx")
        with open(cls.published, "wb") as fh:  # a helper sheet first, as in the team's real file
            fh.write(xlsx_bytes([("Trang tính2", [["L(\"", "C3", "\")"], ["L(\"", "C4", "\")"]]),
                                 ("Trang tính1", [["URL", "Title", "Category", "STT"]] +
                                  [[p["URL"], p["Title"], p["Category"], "Công khai"] for p in PUBLISHED])]))
        cls.base = ["--topic-map", os.path.join(d, "topic-map.csv"), "--keyword-map", os.path.join(d, "keyword-map.csv"),
                    "--link-plan", os.path.join(d, "link-plan.csv"), "--year", "2026", "--today", "2026-10-06"]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def export(self, name, *extra):
        out = os.path.join(self.dir, name)
        code, stdout, err = run_main(ep.main, self.base + ["--out", out, *extra])
        self.assertEqual(code, 0, err)
        return out, read_csv(out[:-5] + ".csv"), stdout

    def test_reads_the_sheet_with_a_url_column(self):
        rows = table_io.read_table(self.published, {"url"})
        self.assertEqual(len(rows), len(PUBLISHED))
        self.assertEqual(rows[1]["Title"], "When Did Thanksgiving Day Begin?")

    def test_published_posts_are_updated_linked_and_checked(self):
        out, plan, stdout = self.export("with-published.xlsx", "--published", self.published)
        hub = next(r for r in plan if r["Main Keyword"] == "when is thanksgiving")
        self.assertEqual(hub["URL Blog"], PUBLISHED[0]["URL"])  # update the published post, keep its URL
        history = next(r for r in plan if r["Main Keyword"] == "history of thanksgiving")
        self.assertEqual(history["URL Blog"], PUBLISHED[1]["URL"])  # 'begin' = 'start' = history
        sheet = table_io.read_table(out, {"match"}, sheet="Published Match")
        kinds = {(r["Match"], r["URL"].split("\n")[0]) for r in sheet}
        self.assertIn(("update this post", PUBLISHED[0]["URL"]), kinds)
        update = next(r for r in sheet if r["URL"] == PUBLISHED[0]["URL"])
        self.assertIn("still says 2024", update["Advice"])
        self.assertIn(("duplicate published posts", PUBLISHED[4]["URL"]), kinds)
        games = next(r for r in plan if r["Main Keyword"] == "thanksgiving games")
        self.assertTrue(games["Related Post (Anchor || URL)"].startswith(
            "thanksgiving games shirts for family || " + PUBLISHED[2]["URL"]))  # a live post first
        self.assertNotIn("snoopy", games["Related Post (Anchor || URL)"])  # never a post that names a franchise
        self.assertIn("Published:", stdout)

    def test_a_previous_plan_keeps_stt_team_columns_and_real_urls(self):
        first, plan, _ = self.export("v1.xlsx")
        with open(first[:-5] + ".csv", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        rows[1]["Title SEO"] = "Is Thanksgiving Always on a Thursday?"
        rows[2]["Trạng thái"] = "Đang viết"
        rows[2]["URL Blog"] = "https://printerval.com/real-slug-n123.html"
        rows.append({**{c: "" for c in ep.COLUMNS}, "STT": "99", "Main Keyword": "thanksgiving placemats", "Outline": "H2..."})
        rows.append({**{c: "" for c in ep.COLUMNS}, "STT": "98", "Main Keyword": "an idea nobody touched"})
        rows = [rows[-2], rows[-1]] + rows[:-2][::-1]  # the team re-sorted the sheet
        previous = os.path.join(self.dir, "edited.csv")
        with open(previous, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=ep.COLUMNS)
            w.writeheader()
            w.writerows(rows)
        out, plan2, stdout = self.export("v2.xlsx", "--previous", previous)
        by_kw = {r["Main Keyword"]: r for r in plan2}
        self.assertEqual(by_kw[plan[1]["Main Keyword"]]["STT"], plan[1]["STT"])
        self.assertEqual(by_kw[plan[1]["Main Keyword"]]["Title SEO"], "Is Thanksgiving Always on a Thursday?")
        self.assertEqual(by_kw[plan[2]["Main Keyword"]]["Trạng thái"], "Đang viết")
        self.assertEqual(by_kw[plan[2]["Main Keyword"]]["URL Blog"], "https://printerval.com/real-slug-n123.html")
        self.assertTrue(any("real-slug-n123.html" in r["Internal Link (Anchor || URL)"] for r in plan2))
        self.assertEqual(by_kw["thanksgiving placemats"]["Outline"], "H2...")  # kept: the team worked on it
        self.assertNotIn("an idea nobody touched", by_kw)
        changes = {r["Main Keyword"]: r["Change"] for r in table_io.read_table(out, {"change"}, sheet="Changes")}
        self.assertEqual(changes["thanksgiving placemats"], "kept from the previous plan")
        self.assertEqual(changes["an idea nobody touched"], "dropped")
        self.assertEqual(len({r["STT"] for r in plan2}), len(plan2))  # STT stay unique
        self.assertIn("Changes from the previous plan", stdout)


class PublishedHelpers(unittest.TestCase):
    def test_anchor_from_a_listicle_title(self):
        self.assertEqual(anchor_from_title("Top 21 Thanksgiving T-Shirts for Family to Enhance Your Holiday Spirit"),
                         "thanksgiving t-shirts for family")
        self.assertEqual(anchor_from_title("60+ Cute Gift For Thanksgiving Showing Your Love To Family"),
                         "cute gift for thanksgiving")

    def test_ip_names_are_flagged(self):
        pub = Published([{"URL": "https://printerval.com/a-n1.html", "Title": "Top 22 Snoopy Thanksgiving Sweatshirts"},
                         {"URL": "https://printerval.com/b-n2.html", "Title": "Thanksgiving Sweatshirts"}],
                        watchlist=[re.compile(r"\bsnoopy\b", re.I)])
        self.assertEqual([q["ip"] for q in pub.posts], [True, False])


class OneCommand(unittest.TestCase):
    def test_run_plan_runs_every_step(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "thanksgiving.csv")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(THANKSGIVING)
            script = os.path.join(ROOT, "skills", "printerval-blog-seo", "scripts", "run_plan.py")
            r = subprocess.run([sys.executable, script, src, "--market", "us", "--only", "occasion=thanksgiving",
                                "--out", os.path.join(d, "out"), "--today", "2026-10-06", "--topic-args", "--max-posts 4"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            for step in ("1/5 keyword-clustering", "2/5 topic-map", "3/5 editorial-calendar", "4/5 internal-link-planner",
                         "5/5 final plan", "QA:"):
                self.assertIn(step, r.stdout)
            self.assertTrue(os.path.exists(os.path.join(d, "out", "final-plan.xlsx")))
            bad = subprocess.run([sys.executable, script, src, "--out", os.path.join(d, "x"), "--skills-dir", d],
                                 capture_output=True, text=True)  # the skills are still found next to this one
            self.assertEqual(bad.returncode, 0, bad.stderr)


if __name__ == "__main__":
    unittest.main()
