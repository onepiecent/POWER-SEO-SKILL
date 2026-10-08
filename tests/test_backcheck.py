import copy
import os
import re
import tempfile
import unittest

import helpers
from helpers import EXAMPLES, read_csv, run_main

import cluster_keywords as ck
import kw_backcheck as bc


def kw(keyword, cid, volume=100, market="us", **extra):
    row = {f: "" for f in ck.KW_FIELDS}
    row.update(cluster_id=cid, market=market, keyword=keyword, volume=volume,
               normalized_keyword=" ".join(sorted(keyword.split())))
    row.update(extra)
    return row


def cl(cid, name, market="us", **extra):
    row = {f: "" for f in ck.CL_FIELDS}
    row.update(cluster_id=cid, market=market, cluster_name=name, seed_basis="max_volume", **extra)
    return row


def urls(*ids):
    return {f"site{i}.com/page" for i in ids}


def by_check(issues, check):
    return [i for i in issues if i["check"] == check]


class BackCheck(unittest.TestCase):
    def test_duplicate_across_groups(self):
        rows = [kw("nurse gift ideas", "C1", 1000, prior_group="G1", prior_main="nurse gift ideas"),
                kw("gifts for nurses", "C1", 500, prior_group="G1", prior_main="nurse gift ideas"),
                kw("gifts for nurses", "C2", 500, prior_group="G2", prior_main="gifts for nurses", prior_role="main"),
                kw("nurse presents", "C2", 100, prior_group="G2", prior_main="gifts for nurses")]
        serp = {"nurse gift ideas": urls(*range(10)), "gifts for nurses": urls(*range(4, 14))}
        issues = bc.backcheck(rows, [cl("C1", "nurse gift ideas"), cl("C2", "gifts for nurses")], serp, 4)
        dup = by_check(issues, "duplicate_across_groups")
        self.assertEqual(len(dup), 1)
        # it is G2's main, so it leaves G1; the target names G2 by another member (the keyword itself is in both)
        self.assertEqual((dup[0]["severity"], dup[0]["group"], dup[0]["other_group"]), ("high", "G1", "G2"))
        self.assertEqual((dup[0]["proposed_action"], dup[0]["proposed_target"]), ("move_keyword", "nurse presents"))
        self.assertIn("6 shared SERP URLs", dup[0]["evidence"])
        self.assertIn("it is the main", dup[0]["evidence"])
        self.assertFalse(by_check(issues, "secondary_is_other_main"))  # the duplicate is reported once

    def test_secondary_is_other_main_by_parent_topic(self):
        rows = [kw("mothers day gifts", "C1", 5000), kw("mothers day presents", "C1", 300, parent_topic="gifts for mom"),
                kw("gifts for mom", "C2", 8000)]
        issues = bc.backcheck(rows, [cl("C1", "mothers day gifts"), cl("C2", "gifts for mom")])
        sec = by_check(issues, "secondary_is_other_main")
        self.assertEqual(len(sec), 1)
        self.assertEqual((sec[0]["severity"], sec[0]["evidence_type"], sec[0]["other_main"]),
                         ("high", "parent_topic", "gifts for mom"))
        # the group with the bigger main survives the merge
        self.assertEqual((sec[0]["proposed_action"], sec[0]["proposed_keyword"], sec[0]["proposed_target"]),
                         ("merge", "gifts for mom", "mothers day gifts"))

    def test_same_question_groups_by_serp_and_by_words(self):
        rows = [kw("gifts for dad", "C1", 9000), kw("presents for father", "C2", 2000)]
        serp = {"gifts for dad": urls(*range(10)), "presents for father": urls(*range(5, 15))}
        issues = bc.backcheck(rows, [cl("C1", "gifts for dad"), cl("C2", "presents for father")], serp, 4)
        same = by_check(issues, "same_question_groups")
        self.assertEqual(len(same), 1)
        self.assertEqual((same[0]["severity"], same[0]["evidence_type"]), ("high", "serp"))
        self.assertIn("share 5 SERP URLs (threshold 4)", same[0]["evidence"])
        self.assertEqual((same[0]["proposed_keyword"], same[0]["proposed_target"]), ("gifts for dad", "presents for father"))
        self.assertFalse(by_check(bc.backcheck(rows, [cl("C1", "gifts for dad"), cl("C2", "presents for father")], serp, 6),
                                  "same_question_groups"))
        rows = [kw("mom gifts", "C1", 900, normalized_keyword="gift mom"),
                kw("gifts mom", "C2", 300, normalized_keyword="gift mom")]
        same = by_check(bc.backcheck(rows, [cl("C1", "mom gifts"), cl("C2", "gifts mom")]), "same_question_groups")
        self.assertEqual((same[0]["severity"], same[0]["evidence_type"]), ("medium", "lexical"))

    def test_weak_member_by_serp_and_by_words(self):
        rows = [kw("gifts for teachers", "C1", 4000), kw("teacher mug ideas", "C1", 700), kw("teacher mugs", "C2", 2000)]
        serp = {"gifts for teachers": urls(*range(10)), "teacher mug ideas": urls(9, *range(20, 29)),
                "teacher mugs": urls(*range(20, 30))}
        weak = by_check(bc.backcheck(rows, [cl("C1", "gifts for teachers"), cl("C2", "teacher mugs")], serp, 4),
                        "weak_member")
        self.assertEqual(len(weak), 1)
        self.assertEqual((weak[0]["severity"], weak[0]["keyword"], weak[0]["proposed_target"]),
                         ("high", "teacher mug ideas", "teacher mugs"))
        self.assertIn("own main 'gifts for teachers' 1/10, with 'teacher mugs' 9/10 (threshold 4)", weak[0]["evidence"])
        # words only: an SEO group's keyword is listed for a SERP check, with no proposal
        seo = dict(prior_group="G1", prior_main="gifts for teachers")
        rows = [kw("gifts for teachers", "C1", 4000, **seo), kw("funny teacher mug ideas", "C1", 700, **seo),
                kw("teacher mug ideas cute", "C2", 2000, prior_group="G2", prior_main="teacher mug ideas cute")]
        cls = [cl("C1", "gifts for teachers", prior_group="G1"), cl("C2", "teacher mug ideas cute", prior_group="G2")]
        weak = by_check(bc.backcheck(rows, cls, sim_t=0.6), "weak_member")
        self.assertEqual((weak[0]["severity"], weak[0]["evidence_type"], weak[0]["proposed_action"]),
                         ("low", "lexical", ""))
        self.assertIn("check both SERPs", weak[0]["evidence"])
        # never for the engine's own clusters, never a keyword bigger than the target group, never a head term
        # moved under a longer phrase that contains it ('thanksgiving date' -> 'thanksgiving date rule')
        plain = [dict(r, prior_group="", prior_main="") for r in rows]
        self.assertFalse(by_check(bc.backcheck(plain, [cl("C1", "gifts for teachers"), cl("C2", "teacher mug ideas cute")],
                                               sim_t=0.6), "weak_member"))
        big = [rows[0], dict(rows[1], volume=5000), rows[2]]
        self.assertFalse([i for i in by_check(bc.backcheck(big, cls, sim_t=0.6), "weak_member") if i["other_main"]])
        head = [kw("when is thanksgiving", "C1", 9000, prior_group="G1", prior_main="when is thanksgiving"),
                kw("thanksgiving date", "C1", 5000, prior_group="G1", prior_main="when is thanksgiving"),
                kw("thanksgiving date rule", "C2", 9000, prior_group="G2", prior_main="thanksgiving date rule")]
        self.assertFalse([i for i in by_check(bc.backcheck(head, [cl("C1", "when is thanksgiving", prior_group="G1"),
                                                                  cl("C2", "thanksgiving date rule", prior_group="G2")],
                                                           sim_t=0.6), "weak_member") if i["other_main"]])

    def test_mixed_intent(self):
        rows = [kw("t shirt printing", "C1", 1000, intents="informational"),
                kw("how to print t shirts", "C1", 500, intents="informational"),
                kw("buy custom t shirts", "C1", 600, intents="transactional"),
                kw("custom t shirts cheap", "C1", 50, intents="transactional")]
        mixed = by_check(bc.backcheck(rows, [cl("C1", "t shirt printing")]), "mixed_intent")
        self.assertEqual(len(mixed), 1)
        self.assertIn("informational only (2 kw, 1,500) vs transactional only (2 kw, 650)", mixed[0]["evidence"])
        self.assertEqual((mixed[0]["proposed_action"], mixed[0]["proposed_keyword"], mixed[0]["proposed_value"]),
                         ("split", "buy custom t shirts", "custom t shirts cheap"))
        rows[2]["volume"] = 100  # 150 of 1,650 = 9%: below the 20% convention
        self.assertFalse(by_check(bc.backcheck(rows, [cl("C1", "t shirt printing")]), "mixed_intent"))

    def test_ungrouped_high_volume_only_in_prior_mode(self):
        rows = [kw("gifts for nurses", "C1", 1000, prior_group="Nurses", prior_main="gifts for nurses"),
                kw("nurse week ideas", "C2", 1500), kw("nurse week themes", "C2", 200)]
        clusters = [cl("C1", "gifts for nurses", prior_group="Nurses"), cl("C2", "nurse week ideas")]
        ung = by_check(bc.backcheck(rows, clusters), "ungrouped_high_volume")
        self.assertEqual(len(ung), 1)
        self.assertEqual((ung[0]["group"], ung[0]["status"], ung[0]["proposed_action"]),
                         ("C2", "applied_default", "keep_keyword"))
        self.assertIn("1,700 searches/month", ung[0]["evidence"])
        self.assertIn("has 1,000", ung[0]["evidence"])
        for r in rows:
            r["prior_group"] = r["prior_main"] = ""
        self.assertFalse(by_check(bc.backcheck(rows, [cl("C1", "gifts for nurses"), cl("C2", "nurse week ideas")]),
                                  "ungrouped_high_volume"))

    def test_main_not_best(self):
        rows = [kw("when is thanksgiving", "C1", 1000), kw("thanksgiving date", "C1", 2500)]
        issues = by_check(bc.backcheck(rows, [cl("C1", "when is thanksgiving")]), "main_not_best")
        self.assertEqual((issues[0]["severity"], issues[0]["proposed_action"], issues[0]["proposed_keyword"]),
                         ("medium", "rename_main", "thanksgiving date"))
        self.assertIn("2.5x the main 'when is thanksgiving' (1,000; threshold 2x)", issues[0]["evidence"])
        rows[1]["volume"] = 1900
        self.assertFalse(by_check(bc.backcheck(rows, [cl("C1", "when is thanksgiving")]), "main_not_best"))

    def test_no_data(self):
        rows = [kw("vintage band tee ideas", "C1", 0), kw("retro band shirts", "C1", "")]
        issues = by_check(bc.backcheck(rows, [cl("C1", "vintage band tee ideas")]), "no_data")
        self.assertEqual((issues[0]["proposed_action"], issues[0]["proposed_value"]),
                         ("research_seed", "vintage band tee ideas|retro band shirts"))
        self.assertIn("None of the group's 2 keywords", issues[0]["evidence"])

    def test_need_conflict(self):
        rows = [kw("custom mugs ideas", "C1", 1300, reader_need="inspire",
                   need_source="conflict: regex shop vs semrush informational")]
        issues = by_check(bc.backcheck(rows, [cl("C1", "custom mugs ideas")]), "need_conflict")
        self.assertEqual((issues[0]["proposed_action"], issues[0]["proposed_value"], issues[0]["status"]),
                         ("set_need", "inspire", "applied_default"))
        self.assertIn("1,300 searches/month", issues[0]["evidence"])

    def test_issue_ids_stable_across_runs_and_row_order(self):
        rows = [kw("when is thanksgiving", "C1", 1000), kw("thanksgiving date", "C1", 2500),
                kw("custom mugs ideas", "C2", 1300, need_source="conflict: regex shop vs semrush informational")]
        clusters = [cl("C1", "when is thanksgiving"), cl("C2", "custom mugs ideas")]
        a = [i["issue_id"] for i in bc.backcheck(rows, clusters)]
        b = [i["issue_id"] for i in bc.backcheck(list(reversed(rows)), list(reversed(clusters)))]
        self.assertEqual(sorted(a), sorted(b))
        self.assertTrue(all(re.fullmatch(r"BC-[0-9a-f]{8}", i) for i in a))
        self.assertEqual(bc.issue_id("main_not_best", "us", "Thanksgiving’s Date", ""),
                         bc.issue_id("main_not_best", "us", "thanksgivings  date", ""))
        lists = [[r[f] for f in ck.KW_FIELDS] for r in rows]  # build_rows' list form gives the same issues
        self.assertEqual(a, [i["issue_id"] for i in bc.backcheck(lists, clusters, kw_fields=ck.KW_FIELDS)])

    def test_proposals_are_not_applied(self):
        rows = [kw("when is thanksgiving", "C1", 1000), kw("thanksgiving date", "C1", 2500)]
        clusters = [cl("C1", "when is thanksgiving")]
        before = copy.deepcopy((rows, clusters))
        with tempfile.TemporaryDirectory() as out:
            line = bc.write_backcheck(out, rows, clusters)
            props = read_csv(os.path.join(out, "proposed-decisions.csv"))
            issues = read_csv(os.path.join(out, "backcheck.csv"))
            report = helpers.read_text(os.path.join(out, "backcheck-report.md"))
        self.assertEqual((rows, clusters), before)
        self.assertEqual(list(props[0]), bc.DECISION_FIELDS)
        self.assertEqual(list(issues[0]), bc.BACKCHECK_FIELDS)
        self.assertEqual((props[0]["decision_id"], props[0]["author"], props[0]["source_issue"]),
                         ("P-" + issues[0]["issue_id"], "proposal", issues[0]["issue_id"]))
        self.assertTrue(props[0]["reason"] and props[0]["evidence"])
        self.assertEqual(issues[0]["status"], "open")
        self.assertIn("| main_not_best | 0 | 1 | 0 | 0 | 1 |", report)
        self.assertIn("1 issues", line)

    def test_raw_mode_backchecks_engine_clusters(self):
        with tempfile.TemporaryDirectory() as out:
            code, stdout, _ = run_main(ck.main, [os.path.join(EXAMPLES, "synthetic-keywords-us.csv"), "--market", "us",
                                                 "--sim", "0.3", "--out", out])
            self.assertEqual(code, 0)
            self.assertIn("Back-check:", stdout)
            for name in ("backcheck.csv", "proposed-decisions.csv", "backcheck-report.md"):
                self.assertTrue(os.path.exists(os.path.join(out, name)), name)
            cluster_ids = {r["cluster_id"] for r in read_csv(os.path.join(out, "clusters.csv"))}
            issues = read_csv(os.path.join(out, "backcheck.csv"))  # may be empty: the engine's clusters can be clean
            self.assertTrue(all(i["group"] in cluster_ids for i in issues))

    def test_shopping_main_keeps_the_research_side(self):
        rows = [kw("christmas mugs", "C1", 12100, prior_group="Mugs", prior_main="christmas mugs", blog_fit="low",
                   reader_need="shop", intents="transactional", serp_features="shopping"),
                kw("how to make custom christmas mugs", "C1", 880, prior_group="Mugs", prior_main="christmas mugs",
                   blog_fit="high", reader_need="how_to", intents="informational"),
                kw("diy christmas mug ideas", "C1", 720, prior_group="Mugs", prior_main="christmas mugs", blog_fit="high",
                   reader_need="inspire", intents="informational")]
        it = by_check(bc.backcheck(rows, [cl("C1", "christmas mugs", prior_group="Mugs")]), "shopping_main")
        self.assertEqual(len(it), 1)
        self.assertEqual((it[0]["severity"], it[0]["proposed_action"], it[0]["proposed_keyword"], it[0]["proposed_value"]),
                         ("high", "split", "how to make custom christmas mugs", "diy christmas mug ideas"))
        self.assertIn("1,600 searches/month", it[0]["evidence"])

    def test_duplicate_listed_in_two_seo_groups_goes_where_it_fits(self):
        """The grouped file kept the keyword in its first group; also_in names the other one."""
        rows = [kw("secret santa gift ideas", "C1", 27100, prior_group="Coworkers", prior_main="secret santa gift ideas"),
                kw("christmas gifts for coworkers", "C1", 18100, prior_group="Coworkers",
                   prior_main="secret santa gift ideas", recipient="coworker"),
                kw("secret santa gifts under 20", "C2", 6600, prior_group="Secret Santa",
                   prior_main="secret santa gifts under 20")]
        rows = [{**r, "normalized_keyword": " ".join(sorted(r["keyword"].split()))} for r in rows]
        issues = bc.backcheck(rows, [cl("C1", "secret santa gift ideas", prior_group="Coworkers"),
                                     cl("C2", "secret santa gifts under 20", prior_group="Secret Santa")],
                              also_in={("us", "secret santa gift ideas"): ["Secret Santa"]})
        dup = by_check(issues, "duplicate_across_groups")
        self.assertEqual(len(dup), 1)
        self.assertEqual((dup[0]["other_group"], dup[0]["status"]), ("Secret Santa", "open"))
        self.assertIn("first in the file", dup[0]["evidence"])
        weak = by_check(issues, "weak_member")  # another recipient: never moved into an unrelated group
        self.assertEqual([(w["keyword"], w["proposed_action"]) for w in weak], [("christmas gifts for coworkers", "split")])


if __name__ == "__main__":
    unittest.main()
