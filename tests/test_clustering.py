import json
import os
import tempfile
import unittest

import helpers
from helpers import EXAMPLES, read_csv, run_main, write_text

import cluster_keywords as ck
import kw_text
from kw_text import Taxonomy, weighted_jaccard

SAMPLE_US = os.path.join(EXAMPLES, "synthetic-keywords-us.csv")


def cluster_names(out_dir):
    return {r["cluster_name"]: r for r in read_csv(os.path.join(out_dir, "clusters.csv"))}


class FacetDetection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tax = Taxonomy.load()

    def facets(self, text):
        return self.tax.detect_facets(kw_text.normalize_text(text))

    def test_dog_mom_is_interest_and_recipient(self):
        f = self.facets("best gifts for dog moms")
        self.assertEqual((f["interest"], f["recipient"]), ("dogs", "mom"))

    def test_occasion_does_not_create_recipient(self):
        f = self.facets("mother's day gifts for grandma")
        self.assertEqual((f["occasion"], f["recipient"]), ("mothers-day", "grandma"))
        f = self.facets("father's day quotes")
        self.assertEqual((f["occasion"], f["recipient"]), ("fathers-day", ""))

    def test_giver_is_not_recipient(self):
        self.assertEqual(self.facets("mother's day gifts from daughter")["recipient"], "")

    def test_uk_forms(self):
        self.assertEqual(self.facets("mothering sunday gifts for nan")["occasion"], "mothers-day")
        self.assertEqual(self.facets("mothering sunday gifts for nan")["recipient"], "grandma")
        self.assertEqual(self.facets("hen do t shirt ideas")["occasion"], "bachelorette")

    def test_morphology(self):
        for kw in ("gifts for fishermen", "fishing gifts for dad", "gifts for anglers"):
            self.assertEqual(self.facets(kw)["interest"], "fishing", kw)

    def test_reader_needs(self):
        cases = {"how to wash a graphic tee": "how_to", "funny t shirt slogans": "copy_ideas",
                 "dtg vs screen printing": "choose", "best gifts for nurses": "choose", "gifts for teachers": "inspire",
                 "when is mother's day": "info", "what resolution do i need for t shirt printing": "info",
                 "custom mugs": "shop", "buy personalized mug": "shop", "t-shirt size chart men": "solve"}
        for kw, want in cases.items():
            norm = kw_text.normalize_text(kw)
            got = self.tax.classify_need(norm, self.tax.detect_facets(norm))
            self.assertEqual(got, want, kw)

    def test_variants_and_years_normalised(self):
        a = self.tax.canon_tokens(kw_text.normalize_text("gifts for mum 2026"))
        b = self.tax.canon_tokens(kw_text.normalize_text("gift for mom"))
        self.assertEqual(set(a), set(b))

    def test_market_terms(self):
        self.assertEqual(self.tax.market_terms("gifts for mum"), "uk")
        self.assertEqual(self.tax.market_terms("gifts for mom"), "us")


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "out")

    def csv(self, name, text):
        p = os.path.join(self.tmp.name, name)
        write_text(p, text)
        return p

    def run_ck(self, *argv):
        code, out, err = run_main(ck.main, list(argv) + ["--out", self.out])
        self.assertEqual(code, 0, out + err)
        return out, err

    def test_sample_clusters(self):
        self.run_ck(SAMPLE_US)
        names = cluster_names(self.out)
        self.assertIn("mother's day gift ideas", names)
        seed = names["mother's day gift ideas"]
        self.assertGreaterEqual(int(seed["keyword_count"]), 3)
        self.assertIn("mothers day gifts", seed["keywords"])
        # different recipient, different interest, giver rather than recipient: separate clusters
        for other in ("mother's day gifts for grandma", "mother's day gift ideas for dog moms",
                      "mother's day gifts from daughter", "mother's day quotes", "when is mother's day"):
            self.assertIn(other, names)
            self.assertNotIn(other, seed["keywords"].split("|")[:1])
        self.assertEqual((names["dog mom gifts"]["interest"], names["dog mom gifts"]["recipient"]), ("dogs", "mom"))
        self.assertEqual(names["custom mugs"]["blog_fit"], "low")
        self.assertEqual(names["how to wash a graphic tee"]["craft"], "care")

    def test_noise_is_excluded_with_reasons_but_legit_terms_kept(self):
        p = self.csv("noise.csv", "keyword,volume\namazon gift ideas,900\nmama bear shirt,800\n"
                                  "regalos para mamá,700\ngifts near me,600\ngifts for dog lovers,500\n"
                                  "printerval reviews,400\nboots for hiking,300\n")
        self.run_ck(p)
        excluded = {r["keyword"]: r["reason"] for r in read_csv(os.path.join(self.out, "excluded.csv"))}
        self.assertEqual(excluded["amazon gift ideas"], "retailer_brand_navigational")
        self.assertEqual(excluded["regalos para mamá"], "spanish_language")
        self.assertEqual(excluded["gifts near me"], "local_intent")
        self.assertEqual(excluded["printerval reviews"], "retailer_brand_navigational")
        kept = {r["keyword"] for r in read_csv(os.path.join(self.out, "keyword-map.csv"))}
        self.assertEqual(kept, {"mama bear shirt", "gifts for dog lovers", "boots for hiking"})

    def test_no_noise_filter(self):
        p = self.csv("noise.csv", "keyword,volume\namazon gift ideas,900\ngifts for dog lovers,500\n")
        self.run_ck(p, "--no-noise-filter")
        self.assertEqual(len(read_csv(os.path.join(self.out, "keyword-map.csv"))), 2)

    def test_variants_years_merge_within_market_only(self):
        p = self.csv("var.csv", "keyword,volume,market\ngifts for mom,1000,us\ngifts for mum,500,us\ngifts for mom 2026,300,us\n"
                                "gifts for mum,900,uk\n")
        self.run_ck(p)
        rows = read_csv(os.path.join(self.out, "clusters.csv"))
        self.assertEqual(sorted((r["market"], r["keyword_count"]) for r in rows), [("uk", "1"), ("us", "3")])
        us = next(r for r in rows if r["market"] == "us")
        self.assertEqual(us["cluster_volume"], "1800")  # the volume of merged variants is added to the cluster

    def test_serp_overlap_beats_vocabulary(self):
        urls = lambda *n: "|".join(f"https://example.com/p{i}" for i in n)  # noqa: E731
        p = self.csv("serp.csv", "keyword,volume,serp_urls\n"
                                 f"gifts for tea lovers,1000,{urls(1, 2, 3, 4, 5, 6)}\n"
                                 f"presents for people who drink tea,500,{urls(1, 2, 3, 4, 9, 10)}\n"
                                 f"gifts for coffee drinkers,400,{urls(1, 2, 20, 21, 22)}\n")
        self.run_ck(p)
        names = cluster_names(self.out)
        self.assertEqual(int(names["gifts for tea lovers"]["keyword_count"]), 2)
        self.assertIn("gifts for coffee drinkers", names)  # only 2 URLs overlap: not merged
        pairs = read_csv(os.path.join(self.out, "merge-candidates.csv"))
        self.assertTrue(any("SERP overlap 2" in r["reason"] for r in pairs))

    def test_filters_only_volume_exclude(self):
        self.run_ck(SAMPLE_US, "--only", "occasion=mothers-day,fathers-day", "--min-volume", "3000")
        rows = read_csv(os.path.join(self.out, "keyword-map.csv"))
        self.assertTrue(rows)
        self.assertTrue(all(r["occasion"] in ("mothers-day", "fathers-day") for r in rows))
        self.assertTrue(all(int(r["volume"]) >= 3000 for r in rows))
        excluded = {r["reason"] for r in read_csv(os.path.join(self.out, "excluded.csv"))}
        self.assertTrue({"filter:only", "filter:min_volume"} <= excluded)

    def test_exclude_regex_and_drop_shop(self):
        self.run_ck(SAMPLE_US, "--exclude", r"\bquotes?\b", "--drop-shop")
        kws = {r["keyword"] for r in read_csv(os.path.join(self.out, "keyword-map.csv"))}
        self.assertNotIn("mother's day quotes", kws)
        self.assertNotIn("custom mugs", kws)

    def test_group_by_and_custom_categories(self):
        cats = os.path.join(EXAMPLES, "categories-example.json")
        self.run_ck(SAMPLE_US, "--categories", cats, "--group-by", "category,occasion")
        groups = read_csv(os.path.join(self.out, "groups.csv"))
        labels = {g["group"] for g in groups}
        self.assertIn("Pets / (none)", labels)
        self.assertTrue(os.path.exists(os.path.join(self.out, "groups.md")))
        names = cluster_names(self.out)
        self.assertEqual(names["gifts for dog lovers"]["category"], "Pets")

    def test_group_by_category_requires_categories(self):
        code, _, err = run_main(ck.main, [SAMPLE_US, "--group-by", "category", "--out", self.out])
        self.assertNotEqual(code, 0)
        self.assertIn("--categories", err)

    def test_extend_taxonomy_reduces_unclassified(self):
        p = self.csv("ext.csv", "keyword,volume\npickleball gifts for dad,2400\ngifts for pickleball players,1900\n"
                                "pickleball gift ideas,880\nrandom unrelated zzz,50\n")
        self.run_ck(p)
        before = len(read_csv(os.path.join(self.out, "unclassified.csv")))
        suggestions = read_csv(os.path.join(self.out, "taxonomy-suggestions.csv"))
        self.assertTrue(any(s["term"] == "pickleball" for s in suggestions))
        self.run_ck(p, "--extend-taxonomy", os.path.join(EXAMPLES, "extend-taxonomy-example.json"))
        after = len(read_csv(os.path.join(self.out, "unclassified.csv")))
        self.assertLess(after, before)

    def test_request_file_and_invalid_key(self):
        req = os.path.join(self.tmp.name, "req.json")
        write_text(req, json.dumps({"files": [SAMPLE_US], "group_by": "occasion", "min_volume": 5000}))
        self.run_ck("--request", req)
        self.assertTrue(os.path.exists(os.path.join(self.out, "groups.csv")))
        self.assertTrue(all(int(r["volume"]) >= 5000 for r in read_csv(os.path.join(self.out, "keyword-map.csv"))))
        write_text(req, json.dumps({"files": [SAMPLE_US], "nonsense": 1}))
        code, _, err = run_main(ck.main, ["--request", req, "--out", self.out])
        self.assertNotEqual(code, 0)
        self.assertIn("nonsense", err)

    def test_file_market_suffix_and_multiple_files(self):
        us = self.csv("us.csv", "keyword,volume\ngifts for mom,1000\n")
        uk = self.csv("uk.csv", "keyword,volume\ngifts for mum,800\n")
        self.run_ck(us + "::us", uk + "::uk")
        rows = read_csv(os.path.join(self.out, "clusters.csv"))
        self.assertEqual(sorted(r["market"] for r in rows), ["uk", "us"])

    def test_gsc_warns_about_impressions(self):
        p = self.csv("gsc.csv", "Top queries,Clicks,Impressions,CTR,Position\nmothers day quotes,120,5400,2.2%,8.4\n")
        _, err = self.run_ck(p)
        self.assertIn("NOT search volume", err)

    def test_parent_topic_is_a_hint_unless_trusted(self):
        p = self.csv("parent.csv", "Keyword,Volume,Parent Topic\nbest gifts for nurses,6600,gifts for nurses\n"
                                   "nurse appreciation gift ideas,2900,gifts for nurses\n")
        self.run_ck(p)
        self.assertEqual(len(read_csv(os.path.join(self.out, "clusters.csv"))), 2)
        pairs = read_csv(os.path.join(self.out, "merge-candidates.csv"))
        self.assertTrue(any("Parent Topic" in r["reason"] for r in pairs))
        self.run_ck(p, "--trust-parent-topic")
        self.assertEqual(len(read_csv(os.path.join(self.out, "clusters.csv"))), 1)

    def test_granularity_changes_cluster_count(self):
        self.run_ck(SAMPLE_US, "--granularity", "tight")
        tight = len(read_csv(os.path.join(self.out, "clusters.csv")))
        self.run_ck(SAMPLE_US, "--granularity", "loose")
        loose = len(read_csv(os.path.join(self.out, "clusters.csv")))
        self.assertGreaterEqual(tight, loose)


class EvidenceAndJoins(unittest.TestCase):
    """M2: one keyword per (market, text) across files, how each keyword joined its cluster, need vs tool intent."""
    KMT = "Keyword,Intent,Volume,Trend,Keyword Difficulty,CPC (USD),Competitive Density,SERP Features,Number of Results\n"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "out")

    def csv(self, name, text):
        p = os.path.join(self.tmp.name, name)
        write_text(p, text)
        return p

    def run_ck(self, *argv):
        code, out, err = run_main(ck.main, list(argv) + ["--out", self.out])
        self.assertEqual(code, 0, out + err)
        return read_csv(os.path.join(self.out, "keyword-map.csv")), cluster_names(self.out)

    def test_same_keyword_in_two_files_is_counted_once(self):
        sem = self.csv("mothers-day_broad-match_us_2026-04-01.csv", self.KMT +
                       '"mothers day gift ideas","Commercial, Informational",40500,"",62,1.10,1.00,"People also ask",1\n')
        ah = self.csv("google_us_mothers-day_matching-terms_2026-04-02_10-00-00.csv",
                      "#,Keyword,Country,Difficulty,Volume,CPC,Parent Keyword,Traffic potential,Intents\n"
                      '1,Mothers Day Gift Ideas,us,48,38000,1.0,mothers day gifts,90000,"Informational,Non-branded"\n')
        kws, names = self.run_ck(sem, ah)
        self.assertEqual(len(kws), 1)
        row = kws[0]
        self.assertEqual((row["volume"], row["volume_sources"]), ("40500", "semrush-kmt:40500|ahrefs-ke:38000"))
        self.assertEqual((row["kd"], row["kd_source"]), ("62", "semrush-kmt"))  # KD from the source of the volume
        self.assertEqual((row["traffic_potential"], row["parent_topic"]), ("90000", "mothers day gifts"))
        self.assertEqual(row["intent_branded"], "0")
        self.assertEqual(row["source_file"], "mothers-day_broad-match_us_2026-04-01.csv|"
                                             "google_us_mothers-day_matching-terms_2026-04-02_10-00-00.csv")
        cl = names["mothers day gift ideas"]
        self.assertEqual((cl["cluster_volume"], cl["keyword_count"]), ("40500", "1"))
        self.assertIn("1 duplicate rows joined", helpers.read_text(os.path.join(self.out, "cluster-report.md")))
        # an exact volume beats an estimate, even a larger one
        kp = self.csv("kp.csv", "Keyword,Avg. monthly searches\nmothers day gift ideas,10K – 100K\n")
        kws, _ = self.run_ck(sem, kp + "::us", "--range-mode", "high")
        self.assertEqual((kws[0]["volume"], kws[0]["volume_estimated"]), ("40500", "0"))
        self.assertEqual(kws[0]["volume_sources"], "semrush-kmt:40500|gkp:~100000")

    def test_positions_duplicate_rows_counted_once(self):
        p = self.csv("printerval.com-organic.Positions-us-20260628-2026-06-29T10_00_00Z.csv",
                     "Keyword,Position,Search Volume,Traffic,URL,Keyword Difficulty,CPC,Keyword Intents,SERP Features by Keyword\n"
                     "gifts for nurses,11,22200,40,https://printerval.com/nurse-mugs,57,1.2,commercial,popular_products\n"
                     "gifts for nurses,4,22200,900,https://printerval.com/blog/gifts-for-nurses,57,1.2,commercial,"
                     "people_also_ask\n")
        kws, names = self.run_ck(p)
        self.assertEqual(len(kws), 1)
        row = kws[0]
        self.assertEqual((row["volume"], row["market"], row["position"]), ("22200", "us", "4"))
        self.assertEqual(row["ranking_url"], "https://printerval.com/blog/gifts-for-nurses")  # the better-ranking URL
        self.assertEqual(row["serp_features"], "paa|shopping")
        self.assertEqual(names["gifts for nurses"]["cluster_volume"], "22200")  # not 44,400

    def test_joined_by_and_grouping_basis(self):
        urls = lambda *n: "|".join(f"https://example.com/p{i}" for i in n)  # noqa: E731
        p = self.csv("serp.csv", "keyword,volume,serp_urls\n"
                                 f"gifts for tea lovers,1000,{urls(1, 2, 3, 4, 5, 6)}\n"
                                 f"presents for people who drink tea,500,{urls(1, 2, 3, 4, 9, 10)}\n"
                                 f"gifts for coffee drinkers,400,{urls(1, 2, 20, 21, 22)}\n"
                                 "gifts for dog lovers,900,\ndog lover gift ideas,300,\n")
        kws, names = self.run_ck(p)
        joined = {r["keyword"]: r["joined_by"] for r in kws}
        self.assertEqual(joined["gifts for tea lovers"], "seed")
        self.assertEqual(joined["presents for people who drink tea"], "serp:4")
        self.assertTrue(joined["dog lover gift ideas"].startswith("lexical:0."), joined)
        tea, dog = names["gifts for tea lovers"], names["gifts for dog lovers"]
        self.assertEqual((tea["grouping_basis"], tea["serp_verified_share"]), ("serp", "1.00"))
        self.assertEqual((dog["grouping_basis"], dog["serp_verified_share"]), ("lexical (not verified by SERP)", "0.00"))
        self.assertEqual((names["gifts for coffee drinkers"]["grouping_basis"], tea["seed_basis"]), ("single", "max_volume"))
        pairs = read_csv(os.path.join(self.out, "merge-candidates.csv"))
        serp_pair = next(r for r in pairs if r["evidence_type"] == "serp")
        self.assertEqual((serp_pair["volume_a"], serp_pair["volume_b"]), ("1500", "400"))
        self.assertEqual(serp_pair["keywords_a"], "gifts for tea lovers|presents for people who drink tea")
        self.assertEqual(serp_pair["guard_diff"], "interest: - vs coffee")  # the taxonomy knows coffee, not tea
        checks = read_csv(os.path.join(self.out, "serp-check.csv"))
        self.assertEqual([(c["keyword_a"], c["keyword_b"]) for c in checks],
                         [("gifts for tea lovers", "gifts for coffee drinkers"), ("gifts for dog lovers", "dog lover gift ideas")])
        self.assertIn("separate posts", checks[0]["current_grouping"])
        self.assertIn("grouped by words only", checks[1]["why"])
        self.run_ck(p, "--serp-check-max", "1")
        self.assertEqual(len(read_csv(os.path.join(self.out, "serp-check.csv"))), 1)
        report = helpers.read_text(os.path.join(self.out, "cluster-report.md"))
        self.assertIn("### Evidence coverage", report)
        self.assertIn("| SERP URLs (serp_urls) | 3 | 60% | 1,900 | 61% |", report)
        self.assertIn("Linkage: seed", report)

    def test_consolidated_clusters_are_marked_core(self):
        p = self.csv("tg.csv", "keyword,volume\nwhen is thanksgiving,80000\nwhat day is thanksgiving,40000\n")
        kws, names = self.run_ck(p, "--market", "us")
        self.assertEqual({r["keyword"]: r["joined_by"] for r in kws},
                         {"when is thanksgiving": "seed", "what day is thanksgiving": "core:-"})
        self.assertEqual(names["when is thanksgiving"]["grouping_basis"], "lexical (not verified by SERP)")

    def test_regex_shop_with_informational_intent_stays_in_blog(self):
        p = self.csv("tees_broad-match_us_2026-10-01.csv", self.KMT +
                     '"retro t shirt designs","Informational, Commercial",1900,"",31,0.45,1.00,"Image pack, Popular products",1\n'
                     '"custom mugs",Transactional,74000,"",64,1.12,1.00,"Popular products, Ads top",1\n'
                     '"vintage band tees",,880,"",20,0.30,1.00,"People also ask",1\n')
        kws, _ = self.run_ck(p, "--drop-shop")
        rows = {r["keyword"]: r for r in kws}
        retro = rows["retro t shirt designs"]
        self.assertNotEqual(retro["reader_need"], "shop")
        self.assertNotEqual(retro["blog_fit"], "low")
        self.assertEqual(retro["need_source"], "conflict: regex shop vs semrush commercial+informational")
        self.assertEqual(rows["vintage band tees"]["need_source"], "conflict: regex shop vs SERP features paa")
        self.assertNotIn("custom mugs", rows)  # transactional: still shop, dropped by --drop-shop
        excluded = {r["keyword"]: r["reason"] for r in read_csv(os.path.join(self.out, "excluded.csv"))}
        self.assertEqual(excluded["custom mugs"], "filter:drop_shop")
        kws, _ = self.run_ck(SAMPLE_US)  # no intent column: the regex alone decides, as before
        mugs = next(r for r in kws if r["keyword"] == "custom mugs")
        self.assertEqual((mugs["blog_fit"], mugs["need_source"]), ("low", "rule"))

    def test_spelling_fixes_csv_lists_every_fix(self):
        words = ["dinner", "menu", "games", "crafts", "quotes", "prayer", "recipes", "decor", "trivia", "facts", "history",
                 "songs", "movies", "parade", "turkey", "pie", "sides", "drinks", "nails", "outfits", "cards", "wishes",
                 "poems", "coloring", "printables", "puzzles", "jokes", "memes", "wallpaper", "door", "table", "centerpiece",
                 "napkins", "banner", "wreath", "shirts", "sweaters", "socks", "aprons", "mugs"]
        typos = ["thanksgivng", "thankgiving", "thanksgiing", "thnksgiving", "thansgiving", "thanksgving", "thanksgiviing",
                 "thankssgiving", "thanksgivimg", "thsnksgiving", "thanksgivibg", "tbanksgiving", "thanksfiving"]
        lines = [f"thanksgiving {w},{1000 + i}" for i, w in enumerate(words)]
        lines += [f"{t} ideas for family,{10 + i}" for i, t in enumerate(typos)]
        p = self.csv("tg.csv", "keyword,volume\n" + "\n".join(lines) + "\n")
        self.run_ck(p, "--market", "us")
        fixes = read_csv(os.path.join(self.out, "spelling-fixes.csv"))
        self.assertEqual(list(fixes[0]), ["kind", "from", "to", "keywords_changed", "examples", "from_volume", "to_volume", "vetoed"])
        typo_rows = {r["from"]: r for r in fixes if r["kind"] == "typo"}
        self.assertEqual(set(typo_rows), set(typos))  # all 13, not the 12 examples of the report
        row = typo_rows["thanksgivng"]
        self.assertEqual((row["to"], row["keywords_changed"], row["examples"], row["from_volume"]),
                         ("thanksgiving", "1", "thanksgivng ideas for family", "10"))
        self.assertEqual(row["to_volume"], str(sum(1000 + i for i in range(len(words)))))
        self.assertEqual(row["vetoed"], "")

    def test_cluster_volume_dedup_next_to_sum(self):
        p = self.csv("var.csv", "keyword,volume\nmother's day gifts,49500\nmothers day gifts,49500\nmother day gifts,49500\n"
                                "mothers day gift,49500\nmothers day gifts 2026,1300\n")
        _, names = self.run_ck(p, "--market", "us")
        cl = names["mother's day gifts"]
        self.assertEqual((cl["cluster_volume"], cl["cluster_volume_dedup"], cl["keyword_count"]), ("199300", "50800", "5"))
        report = helpers.read_text(os.path.join(self.out, "cluster-report.md"))
        self.assertIn("50,800 in total, next to a sum of 199,300", report)

    def test_other_markets_excluded_and_market_from_file_name(self):
        p = self.csv("nurse-gifts_phrase-match_uk_2026-09-01.csv", self.KMT + '"gifts for nurses",Commercial,8100,"",40,1,1,"",1\n')
        kws, _ = self.run_ck(p, "--market", "us")
        self.assertEqual(kws[0]["market"], "uk")  # the file name wins over the default market, with a warning
        report = helpers.read_text(os.path.join(self.out, "cluster-report.md"))
        self.assertIn("the file name says market 'uk' but --market is 'us'", report)
        kws, _ = self.run_ck(p + "::us")
        self.assertEqual(kws[0]["market"], "us")  # an explicit ::market always wins
        mixed = self.csv("mixed.csv", "keyword,volume,country\ngifts for nurses,8100,us\nnurse gifts,900,ca\n")
        kws, _ = self.run_ck(mixed)
        self.assertEqual([r["keyword"] for r in kws], ["gifts for nurses"])
        excluded = read_csv(os.path.join(self.out, "excluded.csv"))
        self.assertEqual([(r["keyword"], r["reason"]) for r in excluded], [("nurse gifts", "market:ca")])


class IndexMatchesBruteForce(unittest.TestCase):
    """The inverted index + prefix filter must give the same result as comparing every pair."""

    @staticmethod
    def brute(rows, tax, sim_t):
        rows = sorted(rows, key=lambda r: (-r.volume, r.keyword))
        clusters = []
        for r in rows:
            best, best_score = None, None
            for i, cl in enumerate(clusters):
                seed = cl[0]
                if ck.part_key(seed) != ck.part_key(r):
                    continue
                s = weighted_jaccard(r.tokset, seed.tokset, tax.weak)
                if s >= sim_t and ck.cores_compatible(r.core, seed.core) and (best_score is None or (s, -i) > best_score):
                    best, best_score = i, (s, -i)
            if best is None:
                clusters.append([r])
            else:
                clusters[best].append(r)
        return {frozenset(k.keyword for k in cl) for cl in clusters}

    def kept_rows(self, path, extra=()):
        args = ck.parse_args([path, *extra])
        tax = Taxonomy.load()
        kept, *_ = ck.ingest(args, tax, kw_text.NoiseRules.load(), None)
        rows, _ = ck.dedupe(kept)
        return rows, tax

    def check(self, path, sim_t):
        rows, tax = self.kept_rows(path)
        fast = ck.Clusterer(rows, tax.weak, sim_t, 4, False).run()
        fast_sets = {frozenset(k.keyword for k in cl) for cl in fast}
        self.assertEqual(fast_sets, self.brute(rows, tax, sim_t))

    def test_sample(self):
        for sim_t in (0.45, 0.6, 0.75):
            self.check(SAMPLE_US, sim_t)

    def test_synthetic_3000(self):
        import make_big_fixture
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "big.csv")
            make_big_fixture.main(3000, path)
            for sim_t in (0.45, 0.6):
                self.check(path, sim_t)


if __name__ == "__main__":
    unittest.main()
