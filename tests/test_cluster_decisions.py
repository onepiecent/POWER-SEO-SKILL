"""Decisions file in the cluster step (data contracts C1-C3): applied deterministically and every decision logged."""
import os
import tempfile
import unittest

import helpers  # noqa: F401  (puts the skills' scripts on sys.path)
from helpers import read_csv, run_main, write_text
from test_plan import xlsx_bytes

import cluster_keywords as ck
from kw_decisions import decision_key

HEAD = "decision_id,action,market,keyword,target,value,reason,evidence,source_issue,author,date\n"
KEYWORDS = ("keyword,volume\n"
            "gifts for tea lovers,1000\ntea lover gift ideas,400\ngifts for coffee drinkers,800\n"
            "coffee lover gift ideas,300\ngifts for dog lovers,900\ndog lover gift ideas,300\n"
            "gifts for cat lovers,700\ncat lover gift ideas,200\ngifts for gardeners,600\n"
            "gardening gift ideas,250\ngifts for golfers,550\ngolf gift ideas,240\ngifts for nurses,500\n"
            "nurse gift ideas,230\nblank t shirts,5000\n")


def urls(*n):
    return "|".join(f"https://example.com/p{i}" for i in n)


class ClusterDecisions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "out")

    def file(self, name, text):
        p = os.path.join(self.tmp.name, name)
        write_text(p, text)
        return p

    def run_ck(self, keywords, decisions, *argv):
        code, out, err = run_main(ck.main, [keywords, "--decisions", decisions, "--out", self.out, *argv])
        self.assertEqual(code, 0, out + err)
        self.stdout = out
        log = {r["decision_id"]: r for r in read_csv(os.path.join(self.out, "decisions-log-cluster.csv"))}
        kws = {r["keyword"]: r for r in read_csv(os.path.join(self.out, "keyword-map.csv"))}
        cls = {r["cluster_id"]: r for r in read_csv(os.path.join(self.out, "clusters.csv"))}
        return log, kws, cls

    def test_decision_key(self):
        self.assertEqual(decision_key("  Mother’s-Day_gift   IDEAS "), "mothers day gift ideas")

    def test_each_cluster_action_applied_and_logged(self):
        kw = self.file("kw.csv", KEYWORDS)
        dec = self.file("decisions.csv", HEAD +
                        "D01,drop_keyword,,gifts for golfers,,,off-audience,no print angle,,claude,\n"
                        "D02,keep_keyword,us,blank t shirts,,,we print on blank tees,5000 searches,,seo:lan,\n"
                        "D03,merge,us,gifts for coffee drinkers,coffee lover gift ideas,,same reader,same list,BC-1,claude,\n"
                        "D04,move_keyword,us,dog lover gift ideas,gifts for cat lovers,,r,e,,claude,\n"
                        "D05,split,us,nurse gift ideas,,golf gift ideas,r,e,,claude,\n"
                        "D06,keep_apart,us,gifts for tea lovers,tea lover gift ideas,,r,e,,claude,\n"
                        "D07,rename_main,us,cat lover gift ideas,,,r,e,,claude,\n"
                        "D08,set_need,us,gifts for gardeners,,info,r,e,,claude,\n"
                        "D09,set_pillar,us,gifts for gardeners,none,,r,e,,claude,\n"
                        "D10,merge_posts,us,gifts for gardeners,gardening gift ideas,,r,e,,claude,\n")
        log, kws, cls = self.run_ck(kw + "::us", dec)
        self.assertEqual({i: r["status"] for i, r in log.items()},
                         {**{f"D0{i}": "applied" for i in range(1, 9)}, "D10": "invalid"})  # D09: topic step, not logged
        self.assertEqual(log["D01"]["market"], "us")  # a blank market resolves to the keyword's only market
        self.assertIn("kept despite homework_answers", log["D02"]["detail"])
        self.assertIn("Decisions (cluster step): 8 applied", self.stdout)
        excluded = {r["keyword"]: r["reason"] for r in read_csv(os.path.join(self.out, "excluded.csv"))}
        self.assertEqual(excluded, {"gifts for golfers": "decision:D01"})
        self.assertEqual(kws["blank t shirts"]["decision_ids"], "D02")
        same = lambda a, b: kws[a]["cluster_id"] == kws[b]["cluster_id"]  # noqa: E731
        self.assertTrue(same("coffee lover gift ideas", "gifts for coffee drinkers"))  # merge
        self.assertTrue(same("dog lover gift ideas", "gifts for cat lovers"))  # move
        self.assertTrue(same("golf gift ideas", "nurse gift ideas"))  # split, with a member from another post
        self.assertFalse(same("nurse gift ideas", "gifts for nurses"))
        self.assertFalse(same("tea lover gift ideas", "gifts for tea lovers"))  # keep_apart: the non-main leaves
        self.assertEqual(kws["coffee lover gift ideas"]["joined_by"], "decision:D03")
        coffee = cls[kws["gifts for coffee drinkers"]["cluster_id"]]
        self.assertEqual((coffee["cluster_name"], coffee["grouping_basis"], coffee["decision_ids"]),
                         ("gifts for coffee drinkers", "decision", "D03"))
        cat = cls[kws["gifts for cat lovers"]["cluster_id"]]
        self.assertEqual((cat["cluster_name"], cat["decision_ids"]), ("cat lover gift ideas", "D04|D07"))  # rename_main
        self.assertIn("info: 'gifts for cat lovers' has more volume", log["D07"]["detail"])
        garden = cls[kws["gifts for gardeners"]["cluster_id"]]
        self.assertEqual((garden["reader_need"], garden["blog_fit"]), ("info", "medium"))
        self.assertEqual(kws["gifts for gardeners"]["need_source"], "decision")
        # re-running is deterministic, and a decision already true is logged as such
        dec2 = self.file("decisions2.csv", HEAD + "D01,rename_main,us,gifts for nurses,,,r,e,,claude,\n")
        log, _, _ = self.run_ck(kw + "::us", dec2)
        self.assertEqual(log["D01"]["status"], "already_true")

    def test_claude_merge_contradicted_by_serp_rejected_human_applied_with_warning(self):
        kw = self.file("serp.csv", "keyword,volume,serp_urls\n"
                                   f"gifts for tea lovers,1000,{urls(1, 2, 3, 4, 5)}\n"
                                   f"gifts for coffee drinkers,800,{urls(6, 7, 8, 9, 10)}\n")
        row = "D1,merge,us,gifts for tea lovers,gifts for coffee drinkers,,same gift buyers,KD and need alike,,{},\n"
        log, kws, _ = self.run_ck(kw + "::us", self.file("claude.csv", HEAD + row.format("claude")))
        self.assertEqual(log["D1"]["status"], "rejected_by_data")
        self.assertIn("share 0 URLs", log["D1"]["detail"])
        self.assertNotEqual(kws["gifts for tea lovers"]["cluster_id"], kws["gifts for coffee drinkers"]["cluster_id"])
        log, kws, _ = self.run_ck(kw + "::us", self.file("seo.csv", HEAD + row.format("seo:lan")))
        self.assertEqual(log["D1"]["status"], "applied_with_warning")
        self.assertIn("warning: SERP", log["D1"]["detail"])
        self.assertEqual(kws["gifts for tea lovers"]["cluster_id"], kws["gifts for coffee drinkers"]["cluster_id"])

    def test_missing_reason_or_evidence_invalid(self):
        kw = self.file("kw.csv", KEYWORDS)
        log, kws, _ = self.run_ck(kw + "::us", self.file("d.csv", HEAD +
                                  "D1,merge,us,gifts for tea lovers,gifts for nurses,,,some evidence,,claude,\n"
                                  "D2,drop_keyword,us,gifts for nurses,,,a reason,,,seo:lan,\n"))
        self.assertEqual((log["D1"]["status"], log["D2"]["status"]), ("invalid", "invalid"))
        self.assertIn("reason empty", log["D1"]["detail"])
        self.assertIn("gifts for nurses", kws)  # nothing applied
        self.assertNotEqual(kws["gifts for tea lovers"]["cluster_id"], kws["gifts for nurses"]["cluster_id"])

    def test_stale_decision_reported_with_closest_keyword(self):
        kw = self.file("kw.csv", KEYWORDS)
        log, _, _ = self.run_ck(kw + "::us", self.file("d.csv", HEAD +
                                "D1,merge,us,gifts for tea lover mugs,gifts for nurses,,r,e,,claude,\n"))
        self.assertEqual(log["D1"]["status"], "stale")
        self.assertIn("closest: 'gifts for tea lovers'", log["D1"]["detail"])

    def test_conflicting_decisions_both_conflict(self):
        kw = self.file("kw.csv", KEYWORDS)
        log, kws, _ = self.run_ck(kw + "::us", self.file("d.csv", HEAD +
                                  "D1,merge,us,gifts for tea lovers,gifts for nurses,,r,e,,claude,\n"
                                  "D2,keep_apart,us,gifts for nurses,gifts for tea lovers,,r,e,,seo:lan,\n"
                                  "D3,drop_keyword,us,golf gift ideas,,,r,e,,claude,\n"
                                  "D4,keep_keyword,us,Golf Gift-Ideas,,,r,e,,seo:lan,\n"))
        self.assertEqual({i: r["status"] for i, r in log.items()},
                         {"D1": "conflict", "D2": "conflict", "D3": "conflict", "D4": "conflict"})
        self.assertNotEqual(kws["gifts for tea lovers"]["cluster_id"], kws["gifts for nurses"]["cluster_id"])
        self.assertIn("golf gift ideas", kws)

    def test_us_uk_merge_invalid(self):
        kw = self.file("both.csv", "keyword,volume,country\ngifts for tea lovers,1000,us\n"
                                   "gifts for coffee drinkers,800,uk\ngifts for nurses,500,us\ngifts for nurses,400,uk\n")
        log, _, _ = self.run_ck(kw, self.file("d.csv", HEAD +
                                "D1,merge,,gifts for tea lovers,gifts for coffee drinkers,,r,e,,claude,\n"
                                "D2,merge,us,gifts for tea lovers,gifts for coffee drinkers,,r,e,,seo:lan,\n"
                                "D3,drop_keyword,,gifts for nurses,,,r,e,,seo:lan,\n"
                                "D4,drop_keyword,uk,gifts for nurses,,,r,e,,seo:lan,\n"))
        self.assertEqual([log[i]["status"] for i in ("D1", "D2", "D3", "D4")],
                         ["invalid", "invalid", "invalid", "applied"])
        self.assertIn("markets differ", log["D1"]["detail"])
        self.assertIn("set the market", log["D3"]["detail"])  # blank market, keyword in both markets
        kws = read_csv(os.path.join(self.out, "keyword-map.csv"))
        self.assertEqual([r["market"] for r in kws if r["keyword"] == "gifts for nurses"], ["us"])

    def test_decisions_from_xlsx_sheet(self):
        kw = self.file("kw.csv", KEYWORDS)
        head = HEAD.strip().split(",")
        p = os.path.join(self.tmp.name, "decisions.xlsx")
        with open(p, "wb") as fh:
            fh.write(xlsx_bytes([("Notes", [["read me first"]]),
                                 ("Decisions", [head, ["D7", "merge", "us", "gifts for tea lovers", "gifts for nurses",
                                                       None, "one reader", "shared list items", None, "seo:lan"]])]))
        log, kws, _ = self.run_ck(kw + "::us", p)
        self.assertEqual(log["D7"]["status"], "applied")
        self.assertEqual(kws["gifts for nurses"]["cluster_id"], kws["gifts for tea lovers"]["cluster_id"])

    def test_without_decisions_the_log_is_empty(self):
        kw = self.file("kw.csv", KEYWORDS)
        code, out, err = run_main(ck.main, [kw + "::us", "--out", self.out])
        self.assertEqual(code, 0, out + err)
        self.assertEqual(read_csv(os.path.join(self.out, "decisions-log-cluster.csv")), [])
        self.assertNotIn("Decisions (cluster step)", out)


if __name__ == "__main__":
    unittest.main()
