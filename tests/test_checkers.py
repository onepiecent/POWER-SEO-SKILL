import csv
import json
import os
import tempfile
import unittest

import helpers
from helpers import EXAMPLES, read_csv, read_text, run_main, write_text

import claims_check as cc
import helpful_check as hc
import slot_check as sc

WEAK = os.path.join(EXAMPLES, "draft-weak-demo.md")
GOOD = os.path.join(EXAMPLES, "draft-good-demo.md")


def rules_of(path, market="us", **kw):
    raw = read_text(path)
    rep = hc.run_checks(raw, market, kw.get("post_type", "gift-guide"), kw.get("keyword", ""), kw.get("final", False))
    return rep, {f["rule"] for f in rep.findings}


class HelpfulCheck(unittest.TestCase):
    def test_weak_draft_is_flagged_on_many_dimensions(self):
        rep, rules = rules_of(WEAK, keyword="mother's day gifts for grandma")
        for expected in ("first_hand", "answer_first", "evidence", "voice", "stuffing", "commercial", "market_spelling", "trust"):
            self.assertIn(expected, rules)
        code, out, _ = run_main(hc.main, [WEAK, "--market", "us", "--post-type", "gift-guide"])
        self.assertEqual(code, 1)  # có phát hiện mức high
        self.assertIn("KHÔNG phải điểm của Google", out)

    def test_good_draft_passes(self):
        rep, rules = rules_of(GOOD)
        self.assertFalse([f for f in rep.findings if f["severity"] in ("high", "medium")], rep.findings)
        code, out, _ = run_main(hc.main, [GOOD, "--market", "us", "--post-type", "gift-guide"])
        self.assertEqual(code, 0)

    def test_uk_market_flags_us_spelling(self):
        _, rules = rules_of(GOOD, market="uk")  # bản demo có "favourite" lẫn "personalized"
        self.assertIn("market_spelling", rules)

    def test_final_turns_placeholders_into_errors(self):
        rep, _ = rules_of(WEAK, final=True)
        ph = [f for f in rep.findings if f["rule"] == "placeholders"]
        self.assertEqual(ph[0]["severity"], "high")

    def test_first_hand_phrase_with_experience_tag_is_accepted(self):
        text = "# T\n\nBy A Writer\nUpdated: 2026-01-01\n\nWe tested three mugs in the dishwasher. [EXPERIENCE: QC photo log, Q3]\n\n## Next\nText here.\n"
        rep = hc.run_checks(text, "us", "generic", "", False)
        self.assertNotIn("first_hand", {f["rule"] for f in rep.findings})

    def test_numbers_with_source_link_are_not_flagged(self):
        text = "# T\n\nBy A\nUpdated: 2026-01-01\n\nShoppers planned to spend $284 on average, [NRF says](https://nrf.com/x).\n"
        rep = hc.run_checks(text, "us", "generic", "", False)
        self.assertEqual(rep.metrics["unsupported_number_sentences"], 0)
        bare = hc.run_checks(text.replace("[NRF says](https://nrf.com/x)", "NRF says"), "us", "generic", "", False)
        self.assertEqual(bare.metrics["unsupported_number_sentences"], 1)

    def test_json_report(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "r.json")
            run_main(hc.main, [WEAK, "--json", p])
            data = json.loads(read_text(p))
            self.assertIn("score", data)
            self.assertTrue(data["findings"])


class SlotCheck(unittest.TestCase):
    def test_weak_slots_have_errors_and_warnings(self):
        text = read_text(WEAK)
        slots, issues, total, density = sc.analyse(text, "gift-guide")
        self.assertEqual(len(slots), 3)
        msgs = " ".join(i[2] for i in issues)
        self.assertIn("URL", msgs)
        self.assertIn("quảng cáo", msgs)
        self.assertIn("dưới 60 từ", msgs)
        self.assertTrue(any(i[0] == "error" for i in issues))

    def test_good_slots_pass(self):
        slots, issues, *_ = sc.analyse(read_text(GOOD), "gift-guide")
        self.assertEqual(len(slots), 2)
        self.assertEqual(issues, [])
        self.assertEqual(slots[0]["section"], "For the grandma who loves to read")

    def test_export_strip_and_final(self):
        with tempfile.TemporaryDirectory() as d:
            exp, strip = os.path.join(d, "slots.csv"), os.path.join(d, "clean.md")
            code, out, _ = run_main(sc.main, [GOOD, "--export", exp, "--strip", strip])
            self.assertEqual(code, 0)
            rows = read_csv(exp)
            self.assertEqual(len(rows), 2)
            self.assertIn("photo mug", rows[1]["product_idea"])
            clean = read_text(strip)
            self.assertNotIn("PRODUCT-SLOT", clean)
            self.assertIn("Common mistakes", clean)  # bài vẫn còn nguyên khi bỏ slot
            code, out, _ = run_main(sc.main, [GOOD, "--final"])
            self.assertEqual(code, 1)

    def test_missing_fields(self):
        slots, issues, *_ = sc.analyse("# T\n\nSome long enough intro " + "word " * 200 + "\n\n[PRODUCT-SLOT: a mug]\n", "generic")
        self.assertEqual({i[2] for i in issues if i[0] == "error"}, {"thiếu trường 'context:'", "thiếu trường 'why:'"})


class ClaimsCheck(unittest.TestCase):
    def scan(self, text, market="us"):
        return cc.scan(text, market, cc.load_watchlist(cc.DEFAULT_WATCHLIST))

    def test_weak_draft_findings(self):
        findings, waived = self.scan(read_text(WEAK))
        rules = {f["rule"] for f in findings}
        for expected in ("delivery_promise", "review_testimonial", "eco_general", "health_claim", "made_in",
                         "ip_brand", "superlative_guarantee", "first_hand_claim", "price_offer"):
            self.assertIn(expected, rules)
        self.assertEqual(waived, [])
        ip = sorted(f["text"] for f in findings if f["rule"] == "ip_brand")
        self.assertEqual(ip, ["disney", "marvel"])

    def test_good_draft_clean(self):
        findings, _ = self.scan(read_text(GOOD))
        self.assertEqual([f for f in findings if f["severity"] in ("high", "medium")], [])

    def test_waiver_marker_moves_finding(self):
        text = "Our fabric is made in USA. [CLAIM-OK: supplier certificate on file; J. Smith, legal; 2026-10-01]"
        findings, waived = self.scan(text)
        self.assertEqual([f for f in findings if f["rule"] == "made_in"], [])
        self.assertTrue(any(w["rule"] == "made_in" and "supplier certificate" in w["waiver"] for w in waived))

    def test_experience_tag_clears_first_hand(self):
        findings, _ = self.scan("We tested the mug in a dishwasher. [EXPERIENCE: QC log]")
        self.assertNotIn("first_hand_claim", {f["rule"] for f in findings})

    def test_budget_phrases_are_not_price_claims(self):
        findings, _ = self.scan("Gift ideas under $25 for every teacher.")
        self.assertNotIn("price_offer", {f["rule"] for f in findings})
        findings, _ = self.scan("Get 20% off today.")
        self.assertIn("price_offer", {f["rule"] for f in findings})

    def test_market_note_for_uk_slots(self):
        findings, _ = self.scan("Text. [PRODUCT-SLOT: mug | context: x y z | why: five words are here ok]", "uk")
        self.assertIn("uk_remit_note", {f["rule"] for f in findings})
        findings, _ = self.scan("Text. [PRODUCT-SLOT: mug | context: x y z | why: five words are here ok]", "us")
        self.assertNotIn("uk_remit_note", {f["rule"] for f in findings})

    def test_keyword_mode_flags_ip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "k.csv")
            write_text(p, "keyword,volume\ndisney mom shirt,900\nSpider-Man birthday gifts,800\ngifts for dog lovers,700\n")
            code, out, _ = run_main(cc.main, ["--keywords", p])
            self.assertEqual(code, 0)
            self.assertIn("2 keyword khớp danh sách IP", out)
            self.assertNotIn("dog lovers", out)

    def test_exit_code(self):
        self.assertEqual(run_main(cc.main, [WEAK, "--market", "us"])[0], 1)
        self.assertEqual(run_main(cc.main, [GOOD, "--market", "us"])[0], 0)


if __name__ == "__main__":
    unittest.main()
