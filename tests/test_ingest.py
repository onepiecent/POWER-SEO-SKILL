import codecs
import os
import tempfile
import unicodedata
import unittest

import helpers  # noqa: F401  (sets up sys.path)
from helpers import read_csv, read_text, run_main

import cluster_keywords as ck
import kw_evidence as ev
import kw_ingest as ing
from test_plan import xlsx_bytes

# Headers copied from real exports (references/export-formats.md, level D); the rows are small synthetic examples.
SEMRUSH_KMT_2026 = "Keyword,Intent,Volume,Trend,Keyword Difficulty,CPC (USD),Competitive Density,SERP Features,Number of Results"
SEMRUSH_API = "database;Keyword;Search Volume;Keyword Difficulty Index;Intent"
SEMRUSH_POSITIONS = ("Keyword,Position,Previous position,Search Volume,Keyword Difficulty,CPC,URL,Traffic,Traffic (%),"
                     "Traffic Cost,Competition,Number of Results,Trends,Timestamp,SERP Features by Keyword,Keyword Intents,"
                     "Position Type")
AHREFS_KE_2026 = ("#,Keyword,Country,Difficulty,Volume,CPC,CPS,Parent Keyword,Last Update,SERP Features,Global volume,"
                  "Traffic potential,Global traffic potential,First seen,Intents,Languages,SV trend (03-2024 - 02-2026),"
                  "SV Forecasting trend (03-2026 - 03-2027),Category")
AHREFS_SE = ("Keyword,Volume,KD,CPC,Previous organic traffic,Current organic traffic,Organic traffic change,Previous position,"
             "Current position,Position change,Previous position kind,Current position kind,Current URL,Previous URL,"
             "Branded,Local,Informational,Commercial,Transactional,Navigational")
KP_MONTHS = ["May 2025", "Jun 2025", "Jul 2025", "Aug 2025", "Sep 2025", "Oct 2025", "Nov 2025", "Dec 2025", "Jan 2026",
             "Feb 2026", "Mar 2026", "Apr 2026"]
KP_HEADER = "\t".join(["Keyword", "Currency", "Avg. monthly searches", "Three month change", "YoY change", "Competition",
                       "Competition (indexed value)", "Top of page bid (low range)", "Top of page bid (high range)",
                       "Ad impression share", "Organic impression share", "Organic average position", "In account?",
                       "In plan?"] + [f"Searches: {m}" for m in KP_MONTHS])
KP_PREAMBLE = 'Keyword Stats 2026-05-09 at 21_25_18\n"May 1, 2025 - April 30, 2026"\n'


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


class EvidenceFormats(unittest.TestCase):
    """What the exports carry beyond keyword and volume (M1): every column is either used or listed as ignored."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "out")

    def path(self, name, data):
        p = os.path.join(self.tmp.name, name)
        with open(p, "wb") as fh:
            fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))
        return p

    def run_ck(self, *argv):
        code, out, err = run_main(ck.main, list(argv) + ["--out", self.out])
        self.assertEqual(code, 0, out + err)
        return {r["keyword"]: r for r in read_csv(os.path.join(self.out, "keyword-map.csv"))}, err

    def test_multiline_cell_stays_one_cell(self):
        for eol in ("\n", "\r\n"):
            with self.subTest(eol=repr(eol)):
                p = self.path("topic.csv", eol.join(['Topic,Keywords,Total Volume',
                                                     '"Unique gifts","unique christmas gifts\ndifferent christmas gifts\n'
                                                     'one of a kind christmas presents",4000', '"Gift sets","christmas gift sets",6600', '']))
                rows = list(ing.read_keywords(p))
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0]["keyword"].splitlines(),
                                 ["unique christmas gifts", "different christmas gifts", "one of a kind christmas presents"])
                self.assertEqual((rows[0]["group"], rows[1]["keyword"]), ("Unique gifts", "christmas gift sets"))

    def test_every_sheet_is_read_and_named(self):
        p = self.path("groups.xlsx", xlsx_bytes([
            ("Read me", [["Exported with groups"]]),
            ("Mothers Day", [["Keyword", "Volume"], ["mother's day gift ideas", 60500], ["gifts for mom", 40500]]),
            ("Fathers Day", [["Keyword", "Volume"], ["father's day gift ideas", 74000]]),
            ("Empty", [])]))
        tables = ing.read_tables(p)
        self.assertEqual([t.info["sheet"] for t in tables], ["Mothers Day", "Fathers Day"])
        self.assertEqual(tables[0].info["sheets_read"], ["Mothers Day", "Fathers Day"])
        self.assertEqual(dict(tables[0].info["sheets_skipped"]),
                         {"Read me": "no keyword column in the first 40 rows", "Empty": "empty"})
        recs = [r for t in tables for r in t]
        self.assertEqual([(r["keyword"], r["_sheet"]) for r in recs],
                         [("mother's day gift ideas", "Mothers Day"), ("gifts for mom", "Mothers Day"),
                          ("father's day gift ideas", "Fathers Day")])
        self.assertNotIn("_sheet", next(iter(ing.read_keywords(p))))  # the one-table reader is unchanged
        kws, _ = self.run_ck(p, "--market", "us")
        self.assertEqual(kws["father's day gift ideas"]["source_file"], "groups.xlsx [Fathers Day]")
        report = read_text(os.path.join(self.out, "cluster-report.md"))
        self.assertIn("Mothers Day, Fathers Day", report)
        self.assertIn("Read me (no keyword column in the first 40 rows)", report)

    def test_semrush_kmt_2026_evidence_columns(self):
        p = self.path("christmas-dress_broad-match_us_2026-10-01.csv", SEMRUSH_KMT_2026 + "\n"
                      '"christmas dress","Commercial, Informational",40500,"0.20,1.00,0.82,0.02,0.01,0.01,0.01,0.01,0.01,0.02,'
                      '0.05,0.09",43,0.87,1.00,"Sitelinks, AI Overview, Image pack, Popular products, People also ask, Ads top",'
                      '3010000000\n'
                      '"christmas dress ideas",Informational,1300,"0.10,1.00,0.50",,0.40,0.80,"Image pack, Things to know",120000000\n')
        t = ing.read_keywords(p)
        rows = list(t)
        self.assertEqual(t.info["source_tool"], "semrush-kmt")
        self.assertEqual((t.info["filename_market"], t.info["filename_date"]), ("us", "2026-10-01"))
        self.assertTrue({"serp_features", "trend", "competitive_density", "results", "intent", "kd", "cpc"} <= set(t.info["columns"]))
        self.assertEqual(t.info["ignored_columns"], [])
        kws, _ = self.run_ck(p)
        dress = kws["christmas dress"]
        self.assertEqual(dress["market"], "us")  # from the file name: the file has no market column
        self.assertEqual(dress["intents"], "commercial|informational")
        self.assertEqual(dress["serp_features"], "ads|ai_overview|image_pack|paa|shopping|sitelinks")
        self.assertEqual(dress["trend"].split(",")[:2], ["0.20", "1.00"])
        self.assertEqual((dress["trend_end"], dress["peak_month"]), ("", ""))  # a Semrush trend names no months
        self.assertEqual((dress["kd_source"], dress["volume_sources"]), ("semrush-kmt", "semrush-kmt:40500"))
        self.assertEqual(kws["christmas dress ideas"]["kd"], "")  # an empty KD is unknown, never 0
        self.assertEqual(rows[1]["serp_features"], "Image pack, Things to know")
        self.assertIn("file name (_<db>_YYYY-MM-DD)", read_text(os.path.join(self.out, "cluster-report.md")))

    def test_semrush_api_semicolon_kd_database_intent_codes(self):
        p = self.path("semrush-regional-keywords.csv", SEMRUSH_API + "\n"
                      "us;personalized dog mom shirt ideas;880;22;1,0\nuk;personalised dog mum gifts;590;18;3\n"
                      "au;dog mum gifts australia;320;12;0\n")
        t = ing.read_keywords(p)
        rows = list(t)
        self.assertEqual((t.info["delimiter"], t.info["source_tool"]), (";", "semrush-api"))
        self.assertEqual((t.info["columns"]["kd"], t.info["columns"]["market"]), ("Keyword Difficulty Index", "database"))
        self.assertEqual(ev.parse_intent(rows[0]["intent"])[0], {"informational", "commercial"})
        kws, _ = self.run_ck(p)
        self.assertEqual((kws["personalized dog mom shirt ideas"]["kd"], kws["personalized dog mom shirt ideas"]["market"]), ("22", "us"))
        self.assertEqual(kws["personalised dog mum gifts"]["intents"], "transactional")
        excluded = {r["keyword"]: r["reason"] for r in read_csv(os.path.join(self.out, "excluded.csv"))}
        self.assertEqual(excluded["dog mum gifts australia"], "market:au")  # not a silent third market

    def test_semrush_positions_url_and_market_from_filename(self):
        p = self.path("printerval.com-organic.Positions-uk-20260628-2026-06-29T10_00_00Z.csv", SEMRUSH_POSITIONS + "\n"
                      "mothering sunday gifts,4,6,12100,38,0.65,https://printerval.com/blog/mothering-sunday-gifts,480,1.2,310,"
                      '0.84,98000000,"[100,82,64,40,38,35,30,28,33,41,56,74]",2026-06-28,"people_also_ask,ai_overview,image_pack,'
                      'organic",informational,Organic\n'
                      "mothering sunday gifts,11,9,12100,38,0.65,https://printerval.com/mothering-sunday-mugs,40,0.1,25,0.84,"
                      '98000000,"[100,82,64,40,38,35,30,28,33,41,56,74]",2026-06-28,"people_also_ask,popular_products",'
                      '"informational, transactional",Organic\n')
        t = ing.read_keywords(p)
        rows = list(t)
        self.assertEqual(t.info["source_tool"], "semrush-positions")
        self.assertEqual((t.info["filename_market"], t.info["filename_date"], t.info["filename_pattern"]),
                         ("uk", "2026-06-28", "-organic.Positions-<db>-YYYYMMDD"))
        self.assertEqual((rows[0]["ranking_url"], rows[0]["position"], rows[0]["volume"]),
                         ("https://printerval.com/blog/mothering-sunday-gifts", "4", "12100"))
        self.assertEqual(ev.parse_trend(rows[0]["trend"], t.info["columns"]["trend"])[0][:2], (1.0, 0.82))
        self.assertEqual(ev.parse_serp_features(rows[0]["serp_features"]), {"paa", "ai_overview", "image_pack"})
        ignored = [h for h, _ in t.info["ignored_columns"]]
        self.assertTrue({"Previous position", "Traffic", "Competition", "Position Type"} <= set(ignored))

    def test_ahrefs_ke_2026_traffic_potential_sv_trend_gb(self):
        trend = ", ".join(str(v) for v in [2600, 2100, 1300, 900, 700, 600, 600, 700, 900, 1200, 1500, 1800] * 2)
        p = self.path("google_gb_mothers-day_matching-terms_2026-03-01_10-00-00.csv", AHREFS_KE_2026 + "\n"
                      f'1,mothering sunday gift ideas,gb,24,9000,0.5,1.1,mothering sunday gifts,2026-02-27,"People also ask,'
                      f'Thumbnail,Sitelinks,AI Overview",15000,21000,26000,2015-03-01,"Informational,Commercial,Non-branded,'
                      f'Non-local",en,"{trend}","2100, 2500",/Shopping/Gifts\n')
        t = ing.read_keywords(p)
        self.assertEqual(t.info["source_tool"], "ahrefs-ke")
        self.assertEqual((t.info["columns"]["volume"], t.info["columns"]["trend"]), ("Volume", "SV trend (03-2024 - 02-2026)"))
        ignored = dict(t.info["ignored_columns"])
        self.assertIn("never used as volume", ignored["Global volume"])
        self.assertIn("forecast", ignored["SV Forecasting trend (03-2026 - 03-2027)"])
        kws, _ = self.run_ck(p)
        row = kws["mothering sunday gift ideas"]
        self.assertEqual((row["market"], row["volume"], row["traffic_potential"]), ("uk", "9000", "21000"))
        self.assertEqual((row["parent_topic"], row["kd_source"]), ("mothering sunday gifts", "ahrefs-ke"))
        self.assertEqual((row["intents"], row["intent_branded"], row["intent_local"]), ("commercial|informational", "0", "0"))
        self.assertEqual((row["trend_end"], row["peak_month"]), ("2026-02", "Mar"))  # months from the header
        self.assertEqual(row["serp_features"], "ai_overview|paa|sitelinks|thumbnail")

    def test_ahrefs_se_boolean_intents(self):
        p = self.path("ahrefs-organic-keywords.csv", AHREFS_SE + "\n"
                      "funny dad shirts,5400,12,0.9,300,410,110,8,6,2,organic,organic,https://printerval.com/blog/funny-dad-shirts,"
                      ",false,false,true,true,false,false\n"
                      "printerval coupon,320,3,0.2,40,35,-5,2,3,-1,organic,organic,https://printerval.com/coupon,,TRUE,FALSE,"
                      "FALSE,FALSE,TRUE,TRUE\n")
        t = ing.read_keywords(p)
        rows = list(t)
        self.assertEqual(t.info["source_tool"], "ahrefs-se")
        self.assertEqual((t.info["columns"]["position"], t.info["columns"]["ranking_url"]), ("Current position", "Current URL"))
        flags = {c[5:]: rows[1][c] for c in rows[1] if c.startswith("flag_")}
        self.assertEqual(ev.parse_intent(rows[1].get("intent"), flags), (frozenset({"transactional", "navigational"}), True, False))
        kws, _ = self.run_ck(p, "--market", "us", "--no-noise-filter")
        dad = kws["funny dad shirts"]
        self.assertEqual((dad["intents"], dad["intent_branded"], dad["position"]), ("commercial|informational", "0", "6"))
        self.assertEqual(dad["ranking_url"], "https://printerval.com/blog/funny-dad-shirts")

    def test_keyword_planner_buckets_become_ranges(self):
        rows = ["mothers day gifts\tUSD\t50000\t0%\t0%\tHigh\t88", "mothers day mugs\tUSD\t5000\t0%\t0%\tHigh\t90",
                "mothers day shirt ideas\tUSD\t500\t\t\tMedium\t50", "mothers day sweatshirt ideas\tUSD\t0\t\t\tLow\t10"]
        text = KP_PREAMBLE + KP_HEADER + "\n" + "\n".join(r + "\t" * (7 + len(KP_MONTHS)) for r in rows) + "\n"
        p = self.path("Keyword Stats 2026-05-09 at 21_25_18.csv", codecs.BOM_UTF16_LE + text.encode("utf-16-le"))
        t = ing.read_keywords(p)
        self.assertEqual((t.info["source_tool"], t.info["header_row"], len(t.info["monthly_columns"])), ("gkp", 3, 12))
        kws, _ = self.run_ck(p, "--market", "us")
        self.assertEqual({k: (r["volume"], r["volume_estimated"], r["volume_range"]) for k, r in kws.items()},
                         {"mothers day gifts": ("10000", "1", "10K–100K"), "mothers day mugs": ("1000", "1", "1K–10K"),
                          "mothers day shirt ideas": ("100", "1", "100–1K"), "mothers day sweatshirt ideas": ("0", "1", "0–10")})
        self.assertIn("Keyword Planner bucket values read as ranges", read_text(os.path.join(self.out, "cluster-report.md")))
        self.run_ck(p, "--market", "us", "--range-mode", "high")
        self.assertEqual(read_csv(os.path.join(self.out, "keyword-map.csv"))[0]["volume"], "100000")

    def test_keyword_planner_monthly_columns(self):
        months = [880, 720, 720, 880, 1000, 1300, 2400, 4400, 1000, 1300, 2900, 9900]
        text = (KP_PREAMBLE + KP_HEADER + "\n" + "mother's day gifts for grandma\tUSD\t2400\t0%\t10%\tHigh\t88" + "\t" * 8
                + "\t".join(map(str, months)) + "\n")
        p = self.path("kp-full.csv", codecs.BOM_UTF16_LE + text.encode("utf-16-le"))
        t = ing.read_keywords(p)
        self.assertEqual(t.info["monthly_columns"][0], (14, "2025-05"))
        self.assertEqual(t.info["monthly_columns"][-1], (25, "2026-04"))
        rec = next(iter(t))
        self.assertEqual((rec["_monthly"]["2025-12"], rec["change_3m"], rec["change_yoy"]), ("4400", "0%", "10%"))
        kws, _ = self.run_ck(p, "--market", "us")
        row = kws["mother's day gifts for grandma"]
        self.assertEqual((row["volume"], row["volume_estimated"], row["volume_range"]), ("2400", "0", ""))  # exact
        self.assertEqual((row["trend_end"], row["peak_month"]), ("2026-04", "Apr"))
        self.assertEqual(row["trend"].split(",")[7], "4400")

    def test_ignored_columns_reported(self):
        p = self.path("hand.csv", "Keyword,Volume,Owner,Global volume,Notes\ngifts for nurses,22200,Lan,90500,check SERP\n")
        t = ing.read_keywords(p)
        self.assertEqual([h for h, _ in t.info["ignored_columns"]], ["Owner", "Global volume", "Notes"])
        self.run_ck(p, "--market", "us")
        report = read_text(os.path.join(self.out, "cluster-report.md"))
        self.assertIn("### Ignored columns", report)
        self.assertIn("| hand.csv | Owner, Global volume (worldwide volume, not the US/UK market: never used as volume), Notes |", report)
        self.assertIn("### Columns used as evidence", report)

    def test_vietnamese_headers_nfc(self):
        header = unicodedata.normalize("NFD", "Từ khoá,Volume,Cụm,Trạng thái")  # decomposed, as some Mac/Sheets exports
        self.assertNotEqual(header, unicodedata.normalize("NFC", header))
        p = self.path("nhom.csv", header + "\nquà tặng mẹ,100,Mẹ,Đã viết\nmothers day gifts,49500,Mother's Day,\n")
        t = ing.read_keywords(p)
        rows = list(t)
        self.assertEqual(set(t.info["columns"]), {"keyword", "volume", "group", "status"})
        self.assertEqual((rows[1]["keyword"], rows[1]["group"]), ("mothers day gifts", "Mother's Day"))

    def test_global_volume_is_never_volume(self):
        p = self.path("ahrefs.csv", "#,Keyword,Country,Difficulty,Global volume\n1,gifts for nurses,us,57,90500\n")
        t = ing.read_keywords(p)
        self.assertEqual(t.info["volume_source"], "none")
        self.assertNotIn("volume", t.info["columns"])
        self.assertIn("Global volume", dict(t.info["ignored_columns"]))
        kws, err = self.run_ck(p)
        self.assertEqual(kws["gifts for nurses"]["volume"], "0")
        self.assertIn("no volume", err)

    def test_gsc_row_cap_and_country_filter(self):
        rows = "".join(f"gift idea {i},{i % 7},{100 + i},1.0%,9.0\n" for i in range(1000))
        p = self.path("Queries.csv", "Top queries,Clicks,Impressions,CTR,Position\n" + rows)
        _, err = self.run_ck(p, "--no-noise-filter")
        self.assertIn("exactly 1,000 rows", err)
        self.assertIn("no Search Console country filter", err)
        self.path("Filters.csv", "Filter,Value\nSearch type,Web\nDate,Last 3 months\nCountry,United Kingdom\n")
        kws, err = self.run_ck(p, "--no-noise-filter")
        self.assertNotIn("country filter", err)
        self.assertEqual(kws["gift idea 5"]["market"], "uk")  # from the Filters sheet
        self.assertIn("Search console filter Country = United Kingdom".lower(),
                      read_text(os.path.join(self.out, "cluster-report.md")).lower())


class EvidenceParsers(unittest.TestCase):
    def test_parse_trend_both_scales(self):
        self.assertEqual(ev.parse_trend("0.20,1.00,0.82", "Trend"), ((0.2, 1.0, 0.82), "relative"))
        self.assertEqual(ev.parse_trend("[100,82,40]", "Trends"), ((1.0, 0.82, 0.4), "relative"))
        self.assertEqual(ev.parse_trend("2181, 1845, 990", "SV trend (09-2024 - 11-2024)"), ((2181.0, 1845.0, 990.0), "absolute"))
        self.assertEqual(ev.trend_header_range("SV trend (09-2024 - 08-2026)"), ("2024-09", "2026-08"))
        self.assertIsNone(ev.trend_header_range("Trend"))
        for raw in ("", "n/a", "12, 40, 7"):  # values above 1 without brackets or an Ahrefs header: unknown form
            self.assertEqual(ev.parse_trend(raw, "Trend"), ((), ""))
        self.assertEqual(ev.peak_month((1, 5, 2), "2026-01"), "Dec")
        self.assertEqual(ev.peak_month((1, 5, 2), ""), "")  # unanchored: no month name

    def test_parse_serp_features_names_codes_snake_case(self):
        self.assertEqual(ev.parse_serp_features("Sitelinks, AI Overview, Image pack, Video carousel, People also ask, "
                                                "Things to know, Discussions and forums, Popular products, Local pack, Ads top"),
                         {"sitelinks", "ai_overview", "image_pack", "video", "paa", "things_to_know", "discussions",
                          "shopping", "local_pack", "ads"})
        self.assertEqual(ev.parse_serp_features("Site Links, People Also Ask, Adwords Bottom, Short Videos"),
                         {"sitelinks", "paa", "ads", "video"})
        self.assertEqual(ev.parse_serp_features("people_also_ask,ai_overview,local_pack,knowledge_graph,organic,paid"),
                         {"paa", "ai_overview", "local_pack", "knowledge_panel", "ads"})
        self.assertEqual(ev.parse_serp_features("People also ask,Top stories,Thumbnail,Featured snippet,Shopping ads"),
                         {"paa", "top_stories", "thumbnail", "featured_snippet", "shopping"})
        self.assertEqual(ev.parse_serp_features("Top Stories, Images, Instant Answer, Hotels Pack, 11"),
                         {"top_stories", "image_pack", "instant_answer", "other:hotels pack", "other:11"})
        self.assertEqual(ev.parse_serp_features(""), frozenset())

    def test_parse_intent_words_codes_letters_flags(self):
        self.assertEqual(ev.parse_intent("Commercial, Informational"), (frozenset({"commercial", "informational"}), None, None))
        self.assertEqual(ev.parse_intent("informational, transactional")[0], {"informational", "transactional"})
        self.assertEqual(ev.parse_intent("1,0")[0], {"informational", "commercial"})  # Semrush API codes
        self.assertEqual(ev.parse_intent("2")[0], {"navigational"})
        self.assertEqual(ev.parse_intent("I, T")[0], {"informational", "transactional"})  # UI badges copied by hand
        self.assertEqual(ev.parse_intent("Informational,Commercial,Non-branded,Non-local"),
                         (frozenset({"informational", "commercial"}), False, False))
        self.assertEqual(ev.parse_intent("Navigational,Branded,Local"), (frozenset({"navigational"}), True, True))
        self.assertEqual(ev.parse_intent("", {"branded": "false", "local": "TRUE", "informational": "true",
                                              "commercial": "false"}), (frozenset({"informational"}), False, True))
        self.assertEqual(ev.parse_intent("-"), (frozenset(), None, None))

    def test_detect_source_tool_and_file_name(self):
        cases = {SEMRUSH_KMT_2026: "semrush-kmt", SEMRUSH_POSITIONS: "semrush-positions", AHREFS_KE_2026: "ahrefs-ke",
                 AHREFS_SE: "ahrefs-se", "Keyword,Search Volume,Keyword Difficulty Index": "semrush-api",
                 "Database,Keyword,Seed keyword,Page,Topic,Page type,Tags,Volume": "semrush-ksb",
                 "Top queries,Clicks,Impressions,CTR,Position": "gsc", KP_HEADER: "gkp",
                 "STT,Main Keyword,Secondary Keyword,Volume,KD,Category,Category Kind,Thuộc Pillar": "team-plan",
                 "keyword,volume": "generic"}
        for header, want in cases.items():
            delim = "\t" if "\t" in header else ";" if ";" in header else ","
            self.assertEqual(ev.detect_source_tool(header.split(delim)), want, header[:40])
        self.assertEqual(ev.detect_source_tool(["Keyword", "Volume"], "gifts_broad-match_us_2026-05-01.csv"), "semrush-kmt")
        names = {"freescout_broad-match_us_2026-05-01.csv": ("us", "2026-05-01", "_<db>_YYYY-MM-DD"),
                 "facet.net-organic.Positions-us-20230918-2023-09-19T20_48_27Z.csv": ("us", "2023-09-18", "-organic.Positions-<db>-YYYYMMDD"),
                 "google_gb_ai-tools_matching-terms_2025-07-08_20-05-24.csv": ("uk", "2025-07-08", "google_<db>_"),
                 "Nicotine-Pouches_clusters_2025-12-15.csv": ("", "2025-12-15", "_(clusters|list)_YYYY-MM-DD"),
                 "my keywords.csv": ("", "", "")}
        for name, want in names.items():
            self.assertEqual(ev.market_date_from_filename(name), want, name)

    def test_kp_bucket_range(self):
        self.assertEqual([ev.kp_bucket_range(v) for v in (0, 50, 500, 5000, 50000.0, 480, 5, None)],
                         ["0–10", "10–100", "100–1K", "1K–10K", "10K–100K", None, None, None])
        self.assertTrue(ev.is_kp_bucketed([50, 500, 0, None], ["", "", "-"]))
        self.assertFalse(ev.is_kp_bucketed([50, 500], ["", "40"]))  # filled months: exact data
        self.assertFalse(ev.is_kp_bucketed([50, 480], []))


if __name__ == "__main__":
    unittest.main()
