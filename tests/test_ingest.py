import codecs
import os
import tempfile
import unittest

import helpers  # noqa: F401  (sets up sys.path)
import kw_ingest as ing


class ParseNumber(unittest.TestCase):
    def test_formats(self):
        cases = [("1,234", True, 1234), ("1.234", True, 1234), ("1.2K", False, 1200), ("2M", False, 2_000_000),
                 ("35%", False, 35), ("$1.25", False, 1.25), ("1.234,5", False, 1234.5), ("12", True, 12)]
        for raw, integer, want in cases:
            with self.subTest(raw=raw):
                self.assertEqual(ing.parse_number(raw, integer=integer)[0], want)

    def test_ranges_and_bounds(self):
        self.assertEqual(ing.parse_number("1K - 10K"), (1000, True))
        self.assertEqual(ing.parse_number("1K – 10K", range_mode="mid"), (5500, True))
        self.assertEqual(ing.parse_number("100 - 1K", range_mode="high"), (1000, True))
        self.assertEqual(ing.parse_number("<10"), (10, True))

    def test_missing(self):
        for raw in ("", "n/a", "-", None, "abc"):
            with self.subTest(raw=raw):
                self.assertIsNone(ing.parse_number(raw)[0])


class Decode(unittest.TestCase):
    def test_encodings(self):
        text = "Keyword\tVolume\nmum gifts\t100\n"
        self.assertEqual(ing.decode_bytes(codecs.BOM_UTF16_LE + text.encode("utf-16-le"))[1], "utf-16")
        self.assertEqual(ing.decode_bytes(text.encode("utf-16-le"))[1], "utf-16-le")
        self.assertEqual(ing.decode_bytes(codecs.BOM_UTF8 + text.encode())[1], "utf-8-sig")
        self.assertEqual(ing.decode_bytes("café".encode("cp1252"))[1], "cp1252")


class ReadKeywords(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def path(self, name, data):
        p = os.path.join(self.tmp.name, name)
        mode = "wb" if isinstance(data, bytes) else "w"
        with open(p, mode, **({} if mode == "wb" else {"encoding": "utf-8"})) as fh:
            fh.write(data)
        return p

    def test_keyword_planner_utf16_tab_with_preamble(self):
        text = ("Keyword Stats 2025-10-01 at 12_00_00\nJan 2025 - Dec 2025\n\n"
                "Keyword\tCurrency\tAvg. monthly searches\tThree month change\tCompetition\tCompetition (indexed value)\n"
                "mother's day gifts\tUSD\t100K – 1M\t0%\tHigh\t88\n"
                "personalised mugs\tUSD\t1K – 10K\t0%\tHigh\t90\n")
        p = self.path("kp.csv", codecs.BOM_UTF16_LE + text.encode("utf-16-le"))
        t = ing.read_keywords(p)
        rows = list(t)
        self.assertEqual((t.info["encoding"], t.info["delimiter"], t.info["header_row"]), ("utf-16", "TAB", 4))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["keyword"], "mother's day gifts")
        self.assertEqual(t.info["volume_source"], "volume")
        self.assertNotIn("kd", t.info["columns"])  # "Competition (indexed value)" is not an SEO difficulty

    def test_semrush_style(self):
        p = self.path("sem.csv", 'Keyword,Intent,Volume,Keyword Difficulty,CPC (USD),Competitive Density\n'
                                 '"gifts for dog lovers","Commercial, Informational",27100,58,1.25,0.45\n')
        t = ing.read_keywords(p)
        row = next(iter(t))
        self.assertEqual(t.info["columns"].keys() >= {"keyword", "volume", "kd", "cpc", "intent"}, True)
        self.assertEqual((row["volume"], row["kd"], row["cpc"]), ("27100", "58", "1.25"))
        self.assertEqual(row["intent"], "Commercial, Informational")

    def test_ahrefs_style_bom_country_parent(self):
        p = self.path("ah.csv", codecs.BOM_UTF8.decode("utf-8") + '"Keyword","Country","Difficulty","Volume","Parent Topic"\n'
                                '"gifts for nurses","United States",57,"22,200","gifts for nurses"\n')
        t = ing.read_keywords(p)
        row = next(iter(t))
        self.assertEqual(t.info["encoding"], "utf-8-sig")
        self.assertEqual((row["market"], row["parent"], row["volume"]), ("United States", "gifts for nurses", "22,200"))

    def test_gsc_uses_impressions_as_fallback(self):
        p = self.path("gsc.csv", "Top queries,Clicks,Impressions,CTR,Position\nmothers day quotes,120,5400,2.2%,8.4\n")
        t = ing.read_keywords(p)
        self.assertEqual(t.info["volume_source"], "impressions")
        self.assertEqual(next(iter(t))["impressions"], "5400")

    def test_semicolon_delimiter(self):
        p = self.path("eu.csv", "Keyword;Volume;KD\ngifts for grandma;12.100;46\n")
        t = ing.read_keywords(p)
        self.assertEqual(t.info["delimiter"], ";")
        self.assertEqual(next(iter(t))["volume"], "12.100")

    def test_map_override(self):
        p = self.path("odd.csv", "Search phrase,Monthly demand\nmum gifts,100\n")
        t = ing.read_keywords(p, {"keyword": "Search phrase", "volume": "Monthly demand"})
        row = next(iter(t))
        self.assertEqual((row["keyword"], row["volume"]), ("mum gifts", "100"))

    def test_missing_header_exits_with_hint(self):
        p = self.path("bad.csv", "foo,bar\n1,2\n")
        with self.assertRaises(SystemExit) as cm:
            ing.read_keywords(p)
        self.assertIn("--map keyword=", str(cm.exception))

    def test_blank_lines_skipped(self):
        p = self.path("blank.csv", "keyword,volume\na gift,1\n\n,\nb gift,2\n")
        t = ing.read_keywords(p)
        self.assertEqual(len(list(t)), 2)
        self.assertEqual(t.info["skipped_blank"], 2)


if __name__ == "__main__":
    unittest.main()
