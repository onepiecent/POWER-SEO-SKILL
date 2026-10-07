"""Review, Back-check, Decisions and Not Planned sheets of the final plan (plan_review.py, contract C7)."""
import csv
import os
import tempfile
import unittest
import zipfile

import helpers  # noqa: F401  (sets up sys.path)
from helpers import run_main

import export_plan as ep
import plan_review as pr
import table_io

TOPIC_FIELDS = ["pillar_id", "pillar_type", "pillar_key", "pillar_name", "role", "cluster_id", "primary_keyword",
                "planned_slug", "post_type", "reader_need", "cluster_volume", "priority_score", "bucket", "season",
                "market", "occasion", "recipient", "interest", "product", "craft", "keywords", "parent_hint", "note",
                "theme", "merged_into"]
MAP_FIELDS = ["cluster_id", "market", "keyword", "volume", "kd", "is_seed", "spelling_fixed", "variants",
              "variant_volumes", "joined_by", "need_source", "prior_group", "intents", "serp_features", "decision_ids"]
TOPIC = [
    dict(pillar_id="P1", pillar_type="occasion", pillar_key="thanksgiving", role="pillar", cluster_id="C1",
         primary_keyword="thanksgiving history", planned_slug="thanksgiving-history", post_type="pillar-hub",
         reader_need="info", cluster_volume="5000", priority_score="90", bucket="A", market="us",
         keywords="thanksgiving history|where was the first thanksgiving|thanksgiving history facts"),
    dict(pillar_id="P1", pillar_type="occasion", pillar_key="thanksgiving", role="cluster", cluster_id="C2",
         primary_keyword="when is thanksgiving", planned_slug="when-is-thanksgiving", post_type="explainer",
         reader_need="info", cluster_volume="9000", priority_score="80", bucket="A", market="us",
         keywords="when is thanksgiving|what day is thanksgiving|is thanksgiving always on a thursday"),
    dict(pillar_id="P1", role="merged", cluster_id="C3", primary_keyword="thanksgiving history for kids",
         post_type="merged", reader_need="info", cluster_volume="300", market="us",
         keywords="thanksgiving history for kids", merged_into="thanksgiving-history", note="same question"),
    dict(role="backlog", cluster_id="C4", primary_keyword="thanksgiving jeopardy", post_type="backlog",
         reader_need="inspire", cluster_volume="700", market="us", keywords="thanksgiving jeopardy",
         note="long tail that matches no theme pillar"),
    dict(role="skip", cluster_id="C5", primary_keyword="thanksgiving shirts", post_type="skip", reader_need="shop",
         cluster_volume="1200", market="us", keywords="thanksgiving shirts", note="shopping intent"),
]
KEYWORDS = [
    dict(cluster_id="C1", market="us", keyword="thanksgiving history", volume="2900", kd="40", is_seed="1",
         joined_by="seed", need_source="rule", prior_group="History", intents="informational",
         serp_features="paa|featured_snippet"),
    dict(cluster_id="C1", market="us", keyword="where was the first thanksgiving", volume="1900", kd="35",
         joined_by="serp:4", need_source="rule", prior_group="History", intents="informational"),
    dict(cluster_id="C1", market="us", keyword="thanksgiving history facts", volume="200", kd="20",
         joined_by="lexical:0.62", need_source="rule"),
    dict(cluster_id="C2", market="us", keyword="when is thanksgiving", volume="8000", kd="66", is_seed="1",
         joined_by="seed", need_source="rule", prior_group="Dates", intents="transactional"),
    dict(cluster_id="C2", market="us", keyword="what day is thanksgiving", volume="700", kd="60", joined_by="serp:6"),
    dict(cluster_id="C2", market="us", keyword="is thanksgiving always on a thursday", volume="300", kd="30",
         joined_by="serp:3"),
    dict(cluster_id="C3", market="us", keyword="thanksgiving history for kids", volume="300", kd="15", is_seed="1",
         joined_by="seed"),
]
BACKCHECK = [
    dict(issue_id="BC-aaaa1111", check="weak_member", severity="medium", market="us", group="C1",
         group_main="thanksgiving history", keyword="thanksgiving history facts", keyword_volume="200",
         evidence_type="lexical", evidence="shares no SERP URL with 'thanksgiving history' (0 of 10)",
         proposed_action="move_keyword", proposed_keyword="thanksgiving history facts",
         proposed_target="when is thanksgiving", status="open"),
    dict(issue_id="BC-bbbb2222", check="close_mains", severity="high", market="us", group="C2",
         group_main="when is thanksgiving", keyword="when is thanksgiving", keyword_volume="8000",
         other_main="thanksgiving history", evidence_type="lexical", evidence="2 shared words, no SERP data",
         proposed_action="merge", proposed_keyword="thanksgiving history", proposed_target="when is thanksgiving",
         status="open"),
]
LOG = [
    dict(decision_id="P-BC-bbbb2222", step="cluster", action="merge", market="us", keyword="thanksgiving history",
         target="when is thanksgiving", author="seo", status="applied_with_warning", detail="no SERP data"),
    dict(decision_id="D-001", step="cluster", action="move_keyword", market="us",
         keyword="thanksgiving history facts", target="when is thanksgiving", author="claude",
         status="rejected_by_data", detail="SERP overlap 0 < 3"),
]
EXCLUDED = [dict(keyword="thanksgiving 2019", volume="5000", reason="past_year", source_file="export.csv"),
            dict(keyword="macys parade live stream", volume="900", reason="navigational", source_file="export.csv")]


def write_csv(path, rows, fields=None):
    fields = fields or list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, restval="")
        w.writeheader()
        w.writerows(rows)
    return path


def sheets(path):
    with zipfile.ZipFile(path) as zf:
        shared = table_io._shared(zf)
        return {name: list(table_io._rows(zf, part, shared)) for name, part in table_io._xlsx_sheets(zf)}, \
            [name for name, _ in table_io._xlsx_sheets(zf)]


def as_dicts(rows):
    return [dict(zip(rows[0], r)) for r in rows[1:]]


class ReviewSheets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        d = tmp.name
        cls.topic = write_csv(os.path.join(d, "topic-map.csv"), TOPIC, TOPIC_FIELDS)
        cls.kmap = write_csv(os.path.join(d, "keyword-map.csv"), KEYWORDS, MAP_FIELDS)
        cls.backcheck = write_csv(os.path.join(d, "backcheck.csv"), BACKCHECK, pr.BACKCHECK_COLUMNS)
        cls.log = write_csv(os.path.join(d, "decisions-log-cluster.csv"), LOG, pr.LOG_COLUMNS)
        cls.excluded = write_csv(os.path.join(d, "excluded.csv"), EXCLUDED)
        cls.full, cls.bare = os.path.join(d, "full.xlsx"), os.path.join(d, "bare.xlsx")
        base = ["--topic-map", cls.topic, "--keyword-map", cls.kmap, "--today", "2026-10-07", "--year", "2026"]
        code, out, err = run_main(ep.main, base + ["--out", cls.full, "--backcheck", cls.backcheck,
                                                   "--decision-log", cls.log, "--excluded", cls.excluded])
        assert code == 0, err
        cls.out = out
        code, _, err = run_main(ep.main, base + ["--out", cls.bare])
        assert code == 0, err
        cls.data, cls.names = sheets(cls.full)

    def test_sheets_present_and_keyword_map_still_sheet2(self):
        self.assertEqual(self.names, ["Plan", "Keyword Map", "Schedule", "QA", "Review", "Back-check", "Decisions",
                                      "Not Planned"])
        self.assertEqual(self.data["Plan"][0], ep.COLUMNS)  # the 15 columns, in order
        with zipfile.ZipFile(self.full) as zf:
            sheet2 = list(table_io._rows(zf, "xl/worksheets/sheet2.xml", table_io._shared(zf)))
        self.assertEqual(sheet2[0], ep.MAP_COLUMNS)
        self.assertEqual(sheets(self.bare)[1], ["Plan", "Keyword Map", "Schedule", "QA", "Review", "Not Planned"])
        self.assertIn("Review: 2 posts, 2 without a reviewed angle", self.out)

    def test_review_values_match_inputs(self):
        self.assertEqual(self.data["Review"][0], pr.REVIEW_COLUMNS)
        review = {r["Main Keyword"]: r for r in as_dicts(self.data["Review"])}
        hub = review["thanksgiving history"]
        self.assertEqual((hub["STT"], hub["Market"], hub["Post Type"], hub["Reader Need"]), ("1", "us", "pillar-hub", "info"))
        self.assertEqual((hub["Intent (tool)"], hub["Need vs Intent"]), ("informational", "agree"))
        self.assertEqual(hub["SERP Features (main)"], "paa, featured_snippet")
        self.assertEqual(hub["Grouping Basis"], "mixed; + 1 merged cluster(s) (topic-map)")
        self.assertEqual((hub["SEO Group"], hub["Main Volume"], hub["Owned Volume"], hub["KD"]),
                         ("History", "2900", "5300", "40"))
        self.assertEqual((hub["Keywords"], hub["Biggest Keyword"]), ("4", "thanksgiving history (2,900/mo)"))
        self.assertEqual(hub["Outline Seeds (from this post's keywords)"].split("\n"),
                         ["H2 candidate: where was the first thanksgiving (1,900/mo)",
                          "H2 candidate: thanksgiving history for kids (300/mo)",
                          "H2 candidate: thanksgiving history facts (200/mo)"])
        self.assertEqual(hub["Angle (reviewed)"], "unreviewed")
        self.assertEqual(hub["Open Issues"], "BC-aaaa1111 weak_member (medium)")  # BC-bbbb2222 was decided
        self.assertEqual(hub["Decisions Applied"], "P-BC-bbbb2222 merge (applied_with_warning)")  # not the rejected one
        self.assertEqual(hub["Why This Post"], "owns 4 keywords, 5,300/mo; SERP-verified 91% of the volume; "
                                               "priority A (score 90)")
        dates = review["when is thanksgiving"]
        self.assertEqual((dates["Intent (tool)"], dates["Need vs Intent"], dates["Grouping Basis"]),
                         ("transactional", "conflict", "serp"))
        # 'what day is thanksgiving' only rephrases the main keyword: no outline seed
        self.assertEqual(dates["Outline Seeds (from this post's keywords)"],
                         "H2 candidate: is thanksgiving always on a thursday (300/mo)")

    def test_angle_and_seeds_come_from_the_plan_data(self):
        plan = ep.Plan(TOPIC, KEYWORDS, None, "https://printerval.com/{slug}", 10, "main", 3, 2026)
        plan.angle_of = {"when-is-thanksgiving": "the date each year, for US readers planning the holiday"}
        rows = pr.review_rows(plan, list(plan.rows()), ep.signature, ep.LIGHT)
        angle = pr.REVIEW_COLUMNS.index("Angle (reviewed)")
        self.assertEqual([r[angle] for r in rows],
                         ["unreviewed", "the date each year, for US readers planning the holiday"])
        seeds = pr.REVIEW_COLUMNS.index("Outline Seeds (from this post's keywords)")
        listed = {line.split(": ", 1)[1].rsplit(" (", 1)[0] for r in rows for line in r[seeds].split("\n") if line}
        self.assertLessEqual(listed, {k["keyword"] for k in KEYWORDS})

    def test_not_planned_lists_backlog_skip_merged_and_excluded(self):
        rows = as_dicts(self.data["Not Planned"])
        self.assertEqual(self.data["Not Planned"][0], pr.NOT_PLANNED_COLUMNS)
        got = [(r["Keyword or Cluster"], r["Volume"]) for r in rows]
        self.assertEqual(got, [("thanksgiving shirts", "1200"), ("thanksgiving jeopardy", "700"),
                               ("thanksgiving history for kids", "300"), ("thanksgiving 2019", "5000"),
                               ("macys parade live stream", "900")])
        by_kw = {r["Keyword or Cluster"]: r for r in rows}
        self.assertTrue(by_kw["thanksgiving shirts"]["Where It Went"].startswith("skipped"))
        self.assertTrue(by_kw["thanksgiving jeopardy"]["Where It Went"].startswith("backlog"))
        self.assertEqual(by_kw["thanksgiving jeopardy"]["Reason"], "long tail that matches no theme pillar")
        self.assertEqual(by_kw["thanksgiving history for kids"]["Where It Went"],
                         "merged into STT 1 (thanksgiving history)")
        self.assertEqual((by_kw["thanksgiving 2019"]["Reason"], by_kw["thanksgiving 2019"]["Evidence"]),
                         ("past_year", "source: export.csv"))

    def test_backcheck_status_updated_from_a_log(self):
        rows = {r["issue_id"]: r for r in as_dicts(self.data["Back-check"])}
        self.assertEqual(self.data["Back-check"][0], pr.BACKCHECK_COLUMNS)
        self.assertEqual(rows["BC-bbbb2222"]["status"], "decided:P-BC-bbbb2222")
        self.assertEqual(rows["BC-aaaa1111"]["status"], "open")  # its decision was rejected by the data
        decisions = as_dicts(self.data["Decisions"])
        self.assertEqual([(d["Decision ID"], d["Status"]) for d in decisions],
                         [("P-BC-bbbb2222", "applied_with_warning"), ("D-001", "rejected_by_data")])
        # with the decisions file, source_issue links a decision whose id does not name the issue
        log = [dict(LOG[1], decision_id="D-007", status="applied")]
        decided = pr.backcheck_status(BACKCHECK, log, [{"decision_id": "D-007", "source_issue": "BC-bbbb2222",
                                                        "reason": "r", "evidence": "e"}])
        self.assertEqual([r["status"] for r in decided], ["decided:D-007", "decided:D-007"])  # BC-aaaa1111: same proposal
        self.assertEqual(pr.decision_rows(log, [{"decision_id": "D-007", "reason": "r", "evidence": "e"}])[0][-2:],
                         ["r", "e"])

    def test_one_decision_settles_several_issues(self):
        log = [dict(LOG[1], decision_id="D-009", action="keep_apart", keyword="x", target="y", status="applied")]
        decided = pr.backcheck_status(BACKCHECK, log, [{"decision_id": "D-009", "source_issue": "BC-aaaa1111 | BC-bbbb2222"}])
        self.assertEqual([r["status"] for r in decided], ["decided:D-009", "decided:D-009"])

    def test_decision_key(self):
        self.assertEqual(pr.decision_key("  Mother’s-Day_Gifts  "), "mothers day gifts")


if __name__ == "__main__":
    unittest.main()
