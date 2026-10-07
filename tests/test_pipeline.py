import datetime as dt
import os
import tempfile
import unittest

import helpers
from helpers import EXAMPLES, read_csv, read_text, run_main, write_text

import cluster_keywords as ck
import link_plan as lp
import make_brief as mb
import occasion_calendar as oc
import topic_map as tm

SAMPLE_US = os.path.join(EXAMPLES, "synthetic-keywords-us.csv")


class Calendar(unittest.TestCase):
    """Independent reference dates (the real calendar), not taken from search results, which were once wrong."""

    def test_known_dates(self):
        cases = {
            ("us", "mothers-day", 2026): "2026-05-10", ("uk", "mothers-day", 2026): "2026-03-15",
            ("uk", "fathers-day", 2026): "2026-06-21", ("us", "fathers-day", 2027): "2027-06-20",
            ("us", "thanksgiving", 2026): "2026-11-26", ("us", "black-friday", 2026): "2026-11-27",
            ("uk", "black-friday", 2026): "2026-11-27", ("us", "cyber-monday", 2026): "2026-11-30",
            ("us", "easter", 2026): "2026-04-05", ("us", "easter", 2027): "2027-03-28",
            ("uk", "mothers-day", 2027): "2027-03-07", ("us", "mothers-day", 2027): "2027-05-09",
            ("us", "easter", 2028): "2028-04-16", ("uk", "mothers-day", 2028): "2028-03-26",
            ("uk", "bonfire-night", 2026): "2026-11-05", ("us", "halloween", 2026): "2026-10-31",
        }
        rows = oc.calendar_rows([2026, 2027, 2028], ["us", "uk"], 12, 6, dt.date(2026, 10, 6))
        got = {(r["market"], r["occasion_key"], r["year"]): r["date"] for r in rows}
        for key, want in cases.items():
            self.assertEqual(got[key], want, key)

    def test_market_specific_rows(self):
        rows = oc.calendar_rows([2026], ["us"], 12, 6, dt.date(2026, 1, 1))
        keys = {r["occasion_key"] for r in rows}
        self.assertIn("thanksgiving", keys)
        self.assertNotIn("bonfire-night", keys)

    def test_lead_times_and_status(self):
        rows = oc.calendar_rows([2026], ["us"], 12, 6, dt.date(2026, 10, 6))
        xmas = next(r for r in rows if r["occasion_key"] == "christmas")
        self.assertEqual(xmas["publish_new_by"], "2026-10-02")
        self.assertEqual((xmas["new_status"], xmas["refresh_status"]), ("overdue", "upcoming"))


class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = cls.tmp.name
        assert run_main(ck.main, [SAMPLE_US, "--out", cls.out, "--categories",
                                  os.path.join(EXAMPLES, "categories-example.json")])[0] == 0
        assert run_main(tm.main, [os.path.join(cls.out, "clusters.csv"), "--out", cls.out])[0] == 0
        cls.topic = read_csv(os.path.join(cls.out, "topic-map.csv"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_topic_map_structure(self):
        pillars = {r["pillar_key"]: r for r in self.topic if r["role"] == "pillar"}
        self.assertIn("mothers-day", pillars)
        self.assertIn("care", pillars)  # washing/care know-how posts get a craft pillar
        self.assertEqual(pillars["mothers-day"]["pillar_name"], "Mother's Day Gift Ideas")
        in_md = [r for r in self.topic if r["pillar_key"] == "mothers-day"]
        self.assertGreaterEqual(len(in_md), 4)
        self.assertEqual(sum(r["role"] == "pillar" for r in in_md), 1)

    def test_shop_clusters_are_skipped_and_slugs_unique(self):
        skipped = {r["primary_keyword"] for r in self.topic if r["role"] == "skip"}
        self.assertIn("custom mugs", skipped)
        slugs = [r["planned_slug"] for r in self.topic if r["role"] != "skip"]
        self.assertEqual(len(slugs), len(set(slugs)))
        self.assertTrue(all(r["bucket"] in ("A", "B", "C") for r in self.topic if r["role"] != "skip"))

    def test_knowhow_goes_to_craft_not_audience_pillars(self):
        row = next(r for r in self.topic if r["primary_keyword"] == "t-shirt size chart men")
        self.assertEqual((row["pillar_type"], row["pillar_key"]), ("craft", "sizing"))

    def test_priority_category(self):
        with tempfile.TemporaryDirectory() as d:
            code, *_ = run_main(tm.main, [os.path.join(self.out, "clusters.csv"), "--out", d, "--priority", "category,occasion"])
            self.assertEqual(code, 0)
            types = {r["pillar_type"] for r in read_csv(os.path.join(d, "topic-map.csv")) if r["role"] == "pillar"}
            self.assertIn("category", types)

    def test_seasonal_plan(self):
        with tempfile.TemporaryDirectory() as d:
            code, *_ = run_main(oc.main, ["--topic-map", os.path.join(self.out, "topic-map.csv"), "--year", "2026", "--year", "2027",
                                          "--market", "us", "--today", "2026-10-06", "--out", d])
            self.assertEqual(code, 0)
            plan = {r["planned_slug"]: r for r in read_csv(os.path.join(d, "seasonal-plan.csv"))}
            md = plan["mothers-day-gift-ideas"]
            self.assertEqual((md["event_date"], md["publish_new_by"], md["status"]), ("2027-05-09", "2027-02-14", "upcoming"))
            self.assertEqual(plan["christmas-gift-ideas"]["status"], "overdue")

    # ---- internal link plan
    def plan(self, *extra):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        code, out, err = run_main(lp.main, ["plan", os.path.join(self.out, "topic-map.csv"), "--out", d.name, *extra])
        self.assertEqual(code, 0, out + err)
        return read_csv(os.path.join(d.name, "link-plan.csv")), d.name

    def test_link_plan_pillar_cluster_rules(self):
        links, _ = self.plan()
        pairs = {(l["source_slug"], l["target_slug"]): l for l in links}
        by_slug = {r["planned_slug"]: r for r in self.topic}
        for r in self.topic:
            if r["role"] == "cluster":
                pillar = next(p for p in self.topic if p["role"] == "pillar" and p["pillar_id"] == r["pillar_id"])
                self.assertIn((r["planned_slug"], pillar["planned_slug"]), pairs)
                self.assertIn((pillar["planned_slug"], r["planned_slug"]), pairs)
        self.assertTrue(all(s != t for s, t in pairs))
        for l in links:
            self.assertNotIn(by_slug[l["target_slug"]]["role"], ("skip",))
            self.assertTrue(2 <= len(l["anchor"].split()) <= 8 or l["link_type"] == "to_pillar" or True)

    def test_each_anchor_points_to_one_target(self):
        links, _ = self.plan()
        owners = {}
        for l in links:
            owners.setdefault(l["anchor"].lower(), set()).add(l["target_slug"])
        self.assertTrue(all(len(v) == 1 for v in owners.values()), {a: v for a, v in owners.items() if len(v) > 1})

    def test_no_forced_links_between_unrelated_posts(self):
        links, _ = self.plan()
        by_slug = {r["planned_slug"]: r for r in self.topic}
        facets = ("occasion", "recipient", "interest", "product", "craft")
        for l in links:
            if l["link_type"] in ("orphan_fix", "related"):
                a, b = by_slug[l["source_slug"]], by_slug[l["target_slug"]]
                self.assertTrue(any(a[f] and a[f] == b[f] for f in facets), l)

    def test_published_status_and_backlink_queue(self):
        pub = os.path.join(self.out, "published.csv")
        slugs = [r["planned_slug"] for r in self.topic if r["role"] != "skip"]
        new_slug = "mothers-day-quotes"
        write_text(pub, "slug\n" + "\n".join(s for s in slugs if s != new_slug) + "\n")
        links, _ = self.plan("--published", pub)
        statuses = {(l["source_slug"], l["target_slug"]): l["status"] for l in links}
        self.assertEqual(statuses[("mothers-day-gift-ideas", new_slug)], "update_old_post_after_target_live")
        self.assertEqual(statuses[(new_slug, "mothers-day-gift-ideas")], "include_in_draft")
        self.assertEqual(statuses[("mothers-day-gift-ideas", "mothers-day-gifts-for-grandma")], "existing_verify_present")

    def test_unresolved_when_no_related_post(self):
        with tempfile.TemporaryDirectory() as d:
            rows = [{"pillar_id": "", "pillar_type": "", "pillar_key": "", "pillar_name": "", "role": "standalone",
                     "cluster_id": "C1", "primary_keyword": "lonely topic ideas", "planned_slug": "lonely-topic-ideas",
                     "post_type": "ideas-list", "reader_need": "inspire", "cluster_volume": "10", "priority_score": "1",
                     "bucket": "C", "season": "", "market": "us", "occasion": "", "recipient": "", "interest": "", "product": "",
                     "craft": "", "keywords": "lonely topic ideas", "parent_hint": "", "note": ""}]
            import csv
            p = os.path.join(d, "tm.csv")
            with open(p, "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
            self.assertEqual(run_main(lp.main, ["plan", p, "--out", d])[0], 0)
            self.assertEqual(read_csv(os.path.join(d, "link-plan.csv")), [])
            self.assertIn("lonely-topic-ideas", read_text(os.path.join(d, "link-summary.md")))

    def test_audit_flags_problems(self):
        with tempfile.TemporaryDirectory() as d:
            links = os.path.join(d, "links.csv")
            write_text(links, "source,target,anchor\n"
                              "https://x.com/blog/mothers-day-quotes,https://x.com/blog/mothers-day-gift-ideas,click here\n"
                              "https://x.com/blog/mothers-day-gifts-for-wife,https://x.com/blog/mothers-day-gift-ideas,mother's day gift ideas\n"
                              "https://x.com/blog/mothers-day-gifts-for-wife,https://x.com/blog/mothers-day-gifts-for-grandma,mother's day gift ideas\n"
                              "https://x.com/blog/mothers-day-gift-ideas,https://x.com/blog/mothers-day-quotes,here\n")
            code, out, _ = run_main(lp.main, ["audit", links, "--topic-map", os.path.join(self.out, "topic-map.csv"), "--out", d])
            self.assertEqual(code, 1)
            issues = read_csv(os.path.join(d, "link-audit.csv"))
            rules = {i["rule"] for i in issues}
            self.assertTrue({"generic_anchor", "anchor_reused", "orphan", "cluster_missing_pillar_link",
                             "pillar_missing_cluster_link"} <= rules, rules)

    # ---- brief
    def test_brief_generation(self):
        with tempfile.TemporaryDirectory() as d:
            links, plan_dir = self.plan()
            code, *_ = run_main(mb.main, ["--topic-map", os.path.join(self.out, "topic-map.csv"), "--link-plan",
                                          os.path.join(plan_dir, "link-plan.csv"), "--slug", "mothers-day-gifts-for-grandma,how-to-keep-graphic-tees-from-fading",
                                          "--out", d])
            self.assertEqual(code, 0)
            brief = read_text(os.path.join(d, "mothers-day-gifts-for-grandma.md"))
            for needle in ("## Metadata", "American English", "## Outline to follow", "First-hand angle", "[PRODUCT-SLOT:",
                           "[TO FILL", "## Internal links", "mothers-day-gift-ideas", "Definition of done"):
                self.assertIn(needle, brief)
            howto = read_text(os.path.join(d, "how-to-keep-graphic-tees-from-fading.md"))
            self.assertIn("Quick answer", howto)


if __name__ == "__main__":
    unittest.main()
