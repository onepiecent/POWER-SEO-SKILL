"""Decisions of the topic and export steps (contracts C1-C3) and the run_plan.py wiring (C6)."""
import os
import shutil
import tempfile
import types
import unittest
from unittest import mock

import helpers
from helpers import EXAMPLES, read_csv, run_main, write_text

import cluster_keywords
import export_plan
import plan_decisions
import run_plan
import table_io
import topic_map

HEADER = "decision_id,action,market,keyword,target,value,reason,evidence,source_issue,author,date\n"


def decisions_file(folder, lines, name="decisions.csv"):
    path = os.path.join(folder, name)
    write_text(path, HEADER + "".join(line + "\n" for line in lines))
    return path


class DecisionsBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.base = os.path.join(cls.tmp, "base")
        code, _, err = run_main(cluster_keywords.main, [os.path.join(EXAMPLES, "synthetic-keywords-us.csv"),
                                                        "--market", "us", "--out", cls.base])
        assert code == 0, err

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def topic(self, lines, *extra):
        out = tempfile.mkdtemp(dir=self.tmp)
        dec = decisions_file(out, lines)
        code, stdout, err = run_main(topic_map.main, [os.path.join(self.base, "clusters.csv"), "--out", out,
                                                      "--decisions", dec, *extra])
        self.assertEqual(code, 0, err)
        log = {r["decision_id"]: r for r in read_csv(os.path.join(out, "decisions-log-topic.csv"))}
        rows = {r["primary_keyword"]: r for r in read_csv(os.path.join(out, "topic-map.csv"))}
        return out, log, rows, stdout


class TopicStep(DecisionsBase):
    def test_topic_actions_set_pillar_promote_restore_drop(self):
        _, log, rows, stdout = self.topic([
            "D-01,set_pillar,us,gifts for cat lovers,gifts for dog lovers,,pet gifts,same Parent Topic,,seo:linh,",
            "D-02,promote_pillar,us,gifts for teachers,,,a teacher hub,32500 searches,,claude,",
            "D-03,set_pillar,us,Teacher Appreciation Gift-Ideas,gifts for teachers,,teacher hub,shares teacher,,claude,",
            "D-04,drop_post,us,camping gifts for men,,off-audience,shop pages rank,KD 70,,seo:linh,",
            "D-05,demote_pillar,us,matching family shirts ideas,,,not a hub,3600 searches,,claude,",
            "D-06,set_pillar,us,gifts for nurses,none,,no nurse pillar,2 clusters,,claude,",
            "D-07,set_pillar,us,completely unknown keyword,gifts for dog lovers,,x,y,,claude,",
            "D-08,promote_pillar,us,fishing gifts for dad,,,a,b,,claude,",
            "D-09,demote_pillar,us,fishing gifts for dad,,,a,b,,claude,",
            "D-10,set_title,us,gifts for teachers,,A Title,a,b,,claude,",
            "D-11,restore_backlog,us,gifts for nurses,,,,,,claude,",
        ])
        self.assertNotIn("D-10", log)  # an export action is not logged by the topic step
        status = {k: v["status"] for k, v in log.items()}
        self.assertEqual(status, {"D-01": "applied", "D-02": "applied", "D-03": "applied", "D-04": "applied",
                                  "D-05": "applied", "D-06": "already_true", "D-07": "stale", "D-08": "conflict",
                                  "D-09": "conflict", "D-11": "invalid"})
        dog = rows["gifts for dog lovers"]
        self.assertEqual((rows["gifts for cat lovers"]["role"], rows["gifts for cat lovers"]["pillar_id"]),
                         ("cluster", dog["pillar_id"]))
        self.assertEqual(rows["gifts for teachers"]["role"], "pillar")
        self.assertEqual(rows["teacher appreciation gift ideas"]["pillar_id"], rows["gifts for teachers"]["pillar_id"])
        self.assertEqual(rows["camping gifts for men"]["role"], "skip")
        self.assertIn("off-audience", rows["camping gifts for men"]["note"])
        self.assertEqual(rows["camping gifts for men"]["planned_slug"], "")
        self.assertEqual(rows["matching family shirts ideas"]["role"], "cluster")
        self.assertEqual(rows["gifts for cat lovers"]["decision_ids"], "D-01")
        self.assertEqual(rows["fishing gifts for dad"]["decision_ids"], "")
        self.assertIn("not found", log["D-07"]["detail"])
        self.assertIn("Decisions (topic step)", stdout)

    def test_restore_merged_cluster_and_hand_over_merged_children(self):
        _, before_log, before, _ = self.topic([], "--max-posts", "3")
        self.assertEqual(before["mother's day quotes"]["role"], "merged")
        _, log, rows, _ = self.topic([
            "D-1,restore_backlog,,mother’s day quotes,,,quotes are their own need,40500 searches,,claude,",
            "D-2,drop_post,us,mother's day gift ideas,,merged into the gift guide,duplicate,same SERP,,seo:an,",
        ], "--max-posts", "3")
        self.assertEqual(log["D-1"]["status"], "applied")
        self.assertEqual(rows["mother's day quotes"]["role"], "cluster")
        self.assertEqual(rows["mother's day quotes"]["pillar_id"], before["mother's day quotes"]["pillar_id"])
        self.assertEqual(rows["mother's day gift ideas"]["role"], "skip")
        slugs = {r["planned_slug"] for r in rows.values() if r["planned_slug"]}
        for r in rows.values():  # the clusters merged into the dropped hub point to a planned post
            if r["role"] == "merged":
                self.assertIn(r["merged_into"], slugs, r["primary_keyword"])

    def test_missing_reason_and_conflicting_targets(self):
        _, log, rows, _ = self.topic([
            "D-1,set_pillar,us,gifts for cat lovers,gifts for dog lovers,,a,b,,claude,",
            "D-2,set_pillar,us,gifts for cat lovers,christmas gift ideas,,a,b,,claude,",
            "D-3,promote_pillar,us,gifts for nurses,,,,evidence only,,claude,",
            "D-4,set_pillar,us,gifts for nurses,gifts for cat lovers,,a,b,,claude,",
        ])
        self.assertEqual([log[k]["status"] for k in ("D-1", "D-2", "D-3", "D-4")],
                         ["conflict", "conflict", "invalid", "invalid"])  # D-4: the target is not a pillar hub
        self.assertEqual(rows["gifts for cat lovers"]["role"], "standalone")


class ExportStep(DecisionsBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        code, _, err = run_main(topic_map.main, [os.path.join(cls.base, "clusters.csv"), "--out", cls.base])
        assert code == 0, err

    def export(self, lines, *extra):
        out = tempfile.mkdtemp(dir=self.tmp)
        dec = decisions_file(out, lines)
        code, stdout, err = run_main(export_plan.main, [
            "--topic-map", os.path.join(self.base, "topic-map.csv"), "--keyword-map", os.path.join(self.base, "keyword-map.csv"),
            "--out", os.path.join(out, "final-plan.xlsx"), "--today", "2026-10-07", "--decisions", dec, *extra])
        self.assertEqual(code, 0, err)
        log = {r["decision_id"]: r for r in read_csv(os.path.join(out, "decisions-log-export.csv"))}
        plan = {r["Main Keyword"]: r for r in read_csv(os.path.join(out, "final-plan.csv"))}
        return out, log, plan, stdout

    def test_export_set_outline_fills_empty_team_value_wins(self):
        out = tempfile.mkdtemp(dir=self.tmp)
        prev = os.path.join(out, "previous.csv")
        write_text(prev, "STT,Main Keyword,Title SEO,Outline\n"
                         "1,mother's day gift ideas,Our Team Title,\n"
                         "2,when is mother's day,,\n")
        _, log, plan, stdout = self.export([
            "D-1,set_title,us,mother's day gift ideas,,A Claude Title,a,b,,claude,",
            "D-2,set_outline,us,STT:2,,H2 the date\\nH2 why it moves,PAA,PAA questions,,claude,",
            "D-3,set_angle,,when is mothers day,,Answer the date first,the reader wants a date,featured snippet,,claude,",
            "D-4,set_title,us,STT:2,,Title A,a,b,,claude,",
            "D-5,set_title,us,STT:2,,Title B,a,b,,claude,",
            "D-6,set_meta,us,no such post anywhere,,Meta,a,b,,claude,",
            "D-7,merge,us,a,b,,a,b,,claude,",
            "D-8,set_titel,us,STT:2,,x,a,b,,claude,",
        ], "--previous", prev)
        self.assertEqual(plan["mother's day gift ideas"]["Title SEO"], "Our Team Title")
        self.assertEqual(log["D-1"]["status"], "team_value_kept")
        self.assertIn("skipped: the team's value wins", log["D-1"]["detail"])
        self.assertEqual(plan["when is mother's day"]["Outline"], "H2 the date\nH2 why it moves")
        self.assertEqual((log["D-2"]["status"], log["D-3"]["status"]), ("applied", "applied"))
        self.assertEqual((log["D-4"]["status"], log["D-5"]["status"]), ("conflict", "conflict"))
        self.assertEqual(plan["when is mother's day"]["Title SEO"], "")
        self.assertEqual(log["D-6"]["status"], "stale")
        self.assertNotIn("D-7", log)  # a cluster action is logged by the cluster step
        self.assertEqual(log["D-8"]["status"], "invalid")
        self.assertIn("Decisions (export step)", stdout)

    def test_set_angle_is_stored_per_post(self):
        rows = [{"n": 3, "post": {"primary_keyword": "when is mother's day", "planned_slug": "when-is-mothers-day",
                                  "market": "us"}, "roles": [], "volume": 10}]
        plan = types.SimpleNamespace(team={})
        log, research = plan_decisions.apply([{"decision_id": "A1", "action": "set_angle", "keyword": "STT:3",
                                               "value": "Date first", "reason": "r", "evidence": "e"}], plan, rows)
        self.assertEqual((log[0]["status"], plan.angle_of), ("applied", {"when-is-mothers-day": "Date first"}))
        self.assertEqual(research, [])

    def test_research_seed_never_enters_plan(self):
        out, log, plan, _ = self.export([
            "R-1,research_seed,us,mother's day poems,,mothers day poems|mothers day poems for church,gap,no poems in the file,,claude,",
        ])
        self.assertEqual(log["R-1"]["status"], "applied")
        self.assertNotIn("mother's day poems", plan)
        self.assertFalse(any("poems" in r["Main Keyword"] or "poems" in r["Secondary Keyword"] for r in plan.values()))
        research = table_io.read_table(os.path.join(out, "final-plan.xlsx"), {"topic"}, sheet="Research Next")
        row = next(r for r in research if r["Topic"] == "mother's day poems")
        self.assertEqual(row["Status"], plan_decisions.RESEARCH_STATUS)
        self.assertEqual(row["Seeds To Export"], "mothers day poems\nmothers day poems for church")

    def test_decisions_from_xlsx_sheet(self):
        path = os.path.join(self.tmp, "decisions.xlsx")
        cols = HEADER.strip().split(",")
        export_plan.write_xlsx(path, [
            ("Notes", export_plan.sheet_xml(["note"], [["read me"]], [20])),
            ("Decisions", export_plan.sheet_xml(cols, [["D-1", "drop_post", "us", "camping gifts for men", "", "off",
                                                        "r", "e", "", "seo:an", "2026-10-07"]], [10] * len(cols)))])
        for reader in (topic_map.read_decisions, plan_decisions.read_decisions):
            rows = reader(path)
            self.assertEqual((rows[0]["decision_id"], rows[0]["keyword"], rows[0]["author"]),
                             ("D-1", "camping gifts for men", "seo:an"))
        self.assertEqual(topic_map.decision_key("Mother’s  Day_Gift-Ideas"), plan_decisions.decision_key("mothers day gift ideas"))


class RunPlanWiring(unittest.TestCase):
    def test_run_plan_passes_prior_decisions_and_this_runs_logs(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "out")
            os.makedirs(out)
            stale = os.path.join(out, "decisions-log-export.csv")  # left by an earlier run
            write_text(stale, "decision_id,step,action,market,keyword,target,value,author,status,detail\n")
            os.utime(stale, (1_000_000_000, 1_000_000_000))
            calls = []

            def fake_run(step, cmd):
                calls.append((step, cmd))
                if step.startswith("1/5"):
                    write_text(os.path.join(out, "excluded.csv"), "keyword,reason\n")
                    write_text(os.path.join(out, "backcheck.csv"), "issue_id,severity\nBC-1,high\nBC-2,low\n")
                    write_text(os.path.join(out, "decisions-log-cluster.csv"),
                               "decision_id,step,action,market,keyword,target,value,author,status,detail\n"
                               "D-1,cluster,merge,us,a,b,,claude,applied,\nD-2,cluster,merge,us,c,d,,claude,stale,\n")
                if step.startswith("2/5"):
                    write_text(os.path.join(out, "decisions-log-topic.csv"),
                               "decision_id,step,action,market,keyword,target,value,author,status,detail\n"
                               "D-3,topic,drop_post,us,e,,,claude,rejected_by_data,\n")

            dec = os.path.join(d, "decisions.csv")
            write_text(dec, HEADER)
            with mock.patch.object(run_plan, "run", fake_run):
                code, stdout, err = run_main(run_plan.main, ["--prior", "grouped.xlsx::us", "--decisions", dec,
                                                             "--out", out])
            self.assertEqual(code, 0, err)
            cmds = {step.split()[0]: cmd for step, cmd in calls}
            self.assertEqual(cmds["1/5"][cmds["1/5"].index("--prior") + 1], "grouped.xlsx::us")
            for step in ("1/5", "2/5", "5/5"):
                self.assertEqual(cmds[step][cmds[step].index("--decisions") + 1], dec)
            export = cmds["5/5"]
            self.assertEqual(export[export.index("--backcheck") + 1], os.path.join(out, "backcheck.csv"))
            self.assertEqual(export[export.index("--excluded") + 1], os.path.join(out, "excluded.csv"))
            logs = [export[i + 1] for i, c in enumerate(export) if c == "--decision-log"]
            self.assertEqual([os.path.basename(p) for p in logs], ["decisions-log-cluster.csv", "decisions-log-topic.csv"])
            self.assertIn("Back-check: 2 issues (high 1, medium 0)", stdout)
            self.assertIn("decisions: 1 applied", stdout)
            self.assertIn("1 stale, 1 rejected by data", stdout)
            code, _, err = run_main(run_plan.main, ["--out", out])  # no export and no --prior
            self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
