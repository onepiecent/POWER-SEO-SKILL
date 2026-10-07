"""Input that an SEO specialist already grouped (cluster_keywords.py --prior, kw_prior.py)."""
import os
import tempfile
import unittest

import helpers  # noqa: F401  (puts the skills' scripts on sys.path)
from helpers import read_csv, read_text, run_main, write_text

import cluster_keywords as ck
import kw_prior
from test_plan import xlsx_bytes


class PriorBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "out")

    def path(self, name, content):
        p = os.path.join(self.tmp.name, name)
        if isinstance(content, bytes):
            with open(p, "wb") as fh:
                fh.write(content)
        else:
            write_text(p, content)
        return p

    def run_ck(self, *argv):
        code, out, err = run_main(ck.main, [*argv, "--out", self.out])
        self.assertEqual(code, 0, err)
        kws = {r["keyword"]: r for r in read_csv(os.path.join(self.out, "keyword-map.csv"))}
        cls = read_csv(os.path.join(self.out, "clusters.csv"))
        return kws, cls

    def members(self, kws):
        """{cluster_id: sorted keywords} of keyword-map.csv."""
        out = {}
        for r in kws.values():
            out.setdefault(r["cluster_id"], []).append(r["keyword"])
        return {k: sorted(v) for k, v in out.items()}


class Layouts(PriorBase):
    def test_long_layout_forward_fill(self):
        p = self.path("long.csv", "Keyword,Cluster,Volume\n"
                                  "christmas gift sets,Gift sets,1000\n"
                                  "christmas gift box ideas,,500\n"
                                  "unique christmas gifts,Unique gifts,2400\n"
                                  "different christmas gifts,,300\n")
        recs, info = kw_prior.read_prior(p)
        self.assertEqual(info["layout"], "long")
        self.assertEqual([(r["keyword"], r["group"]) for r in recs],
                         [("christmas gift sets", "Gift sets"), ("christmas gift box ideas", "Gift sets"),
                          ("unique christmas gifts", "Unique gifts"), ("different christmas gifts", "Unique gifts")])
        self.assertEqual(recs[1]["prior_volume"], "500")
        self.assertFalse(any(r["is_main"] for r in recs))  # no main column: the biggest keyword names the group
        kws, cls = self.run_ck("--prior", p + "::us")
        self.assertEqual(len(cls), 2)
        by_group = {c["prior_group"]: c for c in cls}
        self.assertEqual(by_group["Gift sets"]["cluster_name"], "christmas gift sets")
        self.assertEqual(by_group["Gift sets"]["seed_basis"], "max_volume")
        self.assertEqual(kws["christmas gift box ideas"]["prior_main"], "christmas gift sets")

    def test_wide_layout_secondary_list_cells(self):
        p = self.path("wide.csv", 'STT,Main Keyword,Secondary Keywords,Volume\n'
                                  '1,gifts for mom,"mom gifts; presents for mom | gift ideas for mom",8100\n'
                                  '2,gifts for dad,"dad gifts, presents for dad",6600\n'
                                  '3,gifts for nurses,"nurse gifts\nnurse appreciation gifts",900\n')
        recs, info = kw_prior.read_prior(p)
        self.assertEqual(info["layout"], "wide")
        groups = {}
        for r in recs:
            groups.setdefault(r["group"], []).append(r["keyword"])
        self.assertEqual(groups, {"1": ["gifts for mom", "mom gifts", "presents for mom", "gift ideas for mom"],
                                  "2": ["gifts for dad", "dad gifts", "presents for dad"],
                                  "3": ["gifts for nurses", "nurse gifts", "nurse appreciation gifts"]})
        main = next(r for r in recs if r["keyword"] == "gifts for mom")
        self.assertTrue(main["is_main"])
        self.assertEqual(main["prior_volume"], "8100")
        self.assertEqual(next(r for r in recs if r["keyword"] == "mom gifts")["prior_volume"], "")  # main only
        self.assertEqual(kw_prior.split_list("a, b"), ["a", "b"])
        self.assertEqual(kw_prior.split_list("a, b; c"), ["a, b", "c"])  # ',' only when nothing else splits

    def test_team_final_plan_with_keyword_map_sheet(self):
        plan_header = ["STT", "Main Keyword", "Secondary Keyword", "Volume", "KD", "Category", "Category Kind",
                       "Thuộc Pillar", "Title SEO", "Meta Description SEO", "Outline", "Internal Link (Anchor || URL)",
                       "Related Post (Anchor || URL)", "URL Blog", "Trạng thái"]
        p = self.path("final-plan.xlsx", xlsx_bytes([
            ("Plan", [plan_header,
                      [1, "christmas gift ideas", "christmas present ideas", 9900, 40, None, "Pillar"],
                      [2, "christmas gifts for mom", "mom christmas gifts", 2400, 20, None, "Cluster",
                       "christmas gift ideas"]]),
            ("Keyword Map", [["STT", "Main Keyword", "Keyword", "Volume", "KD", "Role"],
                             [1, "christmas gift ideas", "christmas gift ideas", 9900, 40, "main"],
                             [1, "christmas gift ideas", "christmas present ideas", 1600, 35, "secondary"],
                             [1, "christmas gift ideas", "xmas gift ideas", 880, 30, "also covers"],
                             [2, "christmas gifts for mom", "christmas gifts for mom", 2400, 20, "main"],
                             [2, "christmas gifts for mom", "mom christmas gifts", 320, 15, "secondary"]])]))
        recs, info = kw_prior.read_prior(p)
        self.assertEqual(info["layout"], "plan")
        self.assertEqual(info["sheets"], ["Plan", "Keyword Map"])
        by_kw = {r["keyword"]: r for r in recs}
        self.assertEqual(len(recs), 5)  # the Keyword Map sheet is more complete than the Secondary column
        self.assertEqual((by_kw["xmas gift ideas"]["group"], by_kw["xmas gift ideas"]["role"]), ("1", "also covers"))
        self.assertEqual(by_kw["mom christmas gifts"]["pillar"], "christmas gift ideas")
        self.assertEqual(by_kw["mom christmas gifts"]["group_role"], "Cluster")
        kws, cls = self.run_ck("--prior", p + "::us")
        self.assertEqual(len(cls), 2)
        c2 = next(c for c in cls if c["prior_group"] == "2")
        self.assertEqual((c2["cluster_name"], c2["prior_role"], c2["prior_pillar"], c2["grouping_basis"],
                          c2["seed_basis"]),
                         ("christmas gifts for mom", "Cluster", "christmas gift ideas", "prior:seo", "seo main"))
        self.assertEqual(kws["xmas gift ideas"]["prior_role"], "also covers")
        self.assertEqual(kws["xmas gift ideas"]["volume"], "880")


class PriorClustering(PriorBase):
    GROUPED = ("Keyword,Group\n"
               "christmas gift sets,Gift sets\n"
               "christmas gift box ideas,\n"
               "unique christmas gifts,Unique gifts\n"
               "different christmas gifts,\n"
               "one of a kind christmas presents,\n")

    def test_seo_groups_are_kept_not_regrouped(self):
        """The verified failure: the engine regrouped the SEO's two groups (and merged 'thursday' into one)."""
        grouped = self.path("grouped.csv", self.GROUPED)
        export = self.path("export.csv", "Keyword,Volume,Keyword Difficulty\n"
                                         "christmas gift sets,1900,30\n"
                                         "christmas gift box ideas,320,22\n"
                                         "unique christmas gifts,2900,41\n"
                                         "different christmas gifts,210,25\n"
                                         "one of a kind christmas presents,90,18\n"
                                         "is christmas on a thursday,1300,10\n")
        kws, cls = self.run_ck(export + "::us", "--prior", grouped)
        groups = {c["prior_group"]: c for c in cls if c["prior_group"]}
        self.assertEqual(set(groups), {"Gift sets", "Unique gifts"})
        m = self.members(kws)
        self.assertEqual(m[groups["Gift sets"]["cluster_id"]], ["christmas gift box ideas", "christmas gift sets"])
        self.assertEqual(m[groups["Unique gifts"]["cluster_id"]],
                         ["different christmas gifts", "one of a kind christmas presents", "unique christmas gifts"])
        self.assertEqual({c["grouping_basis"] for c in groups.values()}, {"prior:seo"})
        thursday = kws["is christmas on a thursday"]  # the supplement: an export keyword in no group
        self.assertEqual(thursday["prior_group"], "")
        self.assertNotIn(thursday["cluster_id"], {c["cluster_id"] for c in groups.values()})
        self.assertEqual(len(cls), 3)
        self.assertEqual(kws["christmas gift sets"]["joined_by"], "prior:seo")

    def test_export_backfills_volume_kd_intent(self):
        grouped = self.path("grouped.csv", self.GROUPED)
        export = self.path("export.csv", "Keyword,Volume,Keyword Difficulty,Intent\n"
                                         "unique christmas gifts,2900,41,Commercial\n"
                                         "christmas gift sets,1900,30,Transactional\n")
        kws, _ = self.run_ck(export + "::us", "--prior", grouped)
        self.assertEqual((kws["unique christmas gifts"]["volume"], kws["unique christmas gifts"]["kd"],
                          kws["unique christmas gifts"]["intents"], kws["unique christmas gifts"]["market"]),
                         ("2900", "41", "commercial", "us"))  # the market is the exports' only one
        self.assertEqual(kws["unique christmas gifts"]["volume_estimated"], "0")
        self.assertIn("grouped:-", kws["unique christmas gifts"]["volume_sources"])
        missing = kws["one of a kind christmas presents"]  # in no export and no volume in the grouped file
        self.assertEqual((missing["volume"], missing["volume_estimated"], missing["prior_group"]),
                         ("0", "1", "Unique gifts"))
        report = read_text(os.path.join(self.out, "cluster-report.md"))
        self.assertIn("are in no export", report)

    def test_noise_on_pinned_keyword_is_not_an_exclusion(self):
        grouped = self.path("grouped.csv", "Keyword,Group,Volume\n"
                                           "christmas gifts for mom,Mom,2400\n"
                                           "amazon christmas gifts for mom,,90\n")
        export = self.path("export.csv", "Keyword,Volume\n"
                                         "amazon christmas gifts for dad,500\n"
                                         "christmas gifts for dad,1300\n"
                                         "christmas gifts for grandpa,40\n")
        kws, cls = self.run_ck(export + "::us", "--prior", grouped, "--min-volume", "100",
                               "--only", "recipient=mom,dad")
        self.assertEqual(kws["amazon christmas gifts for mom"]["prior_group"], "Mom")  # noise + min-volume: kept
        self.assertNotIn("amazon christmas gifts for dad", kws)  # an export keyword is still filtered
        self.assertNotIn("christmas gifts for grandpa", kws)
        excluded = {r["keyword"] for r in read_csv(os.path.join(self.out, "excluded.csv"))}
        self.assertNotIn("amazon christmas gifts for mom", excluded)
        self.assertIn("amazon christmas gifts for dad", excluded)
        report = read_text(os.path.join(self.out, "cluster-report.md"))
        self.assertIn("match a filter or noise rule and were kept", report)

    def test_mixed_market_group_split_by_market(self):
        grouped = self.path("grouped.csv", "Keyword,Group,Market\n"
                                           "gifts for mom,Mom,us\n"
                                           "gifts for mum,,uk\n"
                                           "mom gift ideas,,us\n")
        kws, cls = self.run_ck("--prior", grouped)
        mom = [c for c in cls if c["prior_group"] == "Mom"]
        self.assertEqual(sorted(c["market"] for c in mom), ["uk", "us"])
        self.assertEqual(kws["gifts for mum"]["market"], "uk")

    def test_raw_mode_leaves_prior_columns_empty(self):
        export = self.path("export.csv", "Keyword,Volume\ngifts for mom,8100\nmom gifts,1000\n")
        kws, cls = self.run_ck(export + "::us")
        self.assertEqual({r["prior_group"] for r in kws.values()} | {c["prior_group"] for c in cls}, {""})
        code, _, err = run_main(ck.main, ["--out", self.out])
        self.assertNotEqual(code, 0)
        self.assertIn("--prior", err)


if __name__ == "__main__":
    unittest.main()
