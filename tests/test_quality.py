"""Plan quality: spelling fixes for split / cut-off / glued words, navigational noise, natural main keywords, post
selection in big pillars, secondary keywords and the plan QA."""
import unittest

import helpers  # noqa: F401  (sets up sys.path)

import cluster_keywords as ck
import export_plan as ep
import kw_text
import plan_qa
import topic_map as tm
from kw_text import Fluency, NoiseRules, Respeller


class SplitAndCutOffWords(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        docs = [["when", "is", "thanksgiving", str(i)] for i in range(120)]
        docs += [["thanksgiving", "day", str(i)] for i in range(100)]
        docs += [["thanksgiving", "date", str(i)] for i in range(20)]
        docs += [["whenis", "thanksgiving"], ["thanksgivi", "g"], ["thanksgiving", "da"], ["is", "real", "thanksgiving"],
                 ["celebrate", "on", "thanksgiving"], ["da", "thanksgiving"]]
        cls.r = Respeller.learn(docs)

    def test_a_space_typed_inside_a_word(self):
        self.assertEqual(self.r.apply("thanksgivi g"), "thanksgiving")

    def test_a_missing_space(self):
        self.assertEqual(self.r.apply("whenis thanksgiving"), "when is thanksgiving")

    def test_a_cut_off_last_word(self):
        self.assertEqual(self.r.apply("thanksgiving da"), "thanksgiving day")
        self.assertEqual(self.r.apply("da thanksgiving"), "da thanksgiving")  # only the last word can be cut off

    def test_real_words_are_never_glued(self):
        self.assertEqual(self.r.apply("is real thanksgiving"), "is real thanksgiving")  # not 'israel'
        self.assertEqual(self.r.apply("celebrate on thanksgiving"), "celebrate on thanksgiving")  # not 'celebration'
        self.assertEqual(self.r.apply("thanksgiving day"), "thanksgiving day")


class NavigationalNoise(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.noise = NoiseRules.load()

    def reason(self, kw):
        return self.noise.check(kw.lower(), kw_text.normalize_text(kw))

    def test_tv_shows_and_media_brands(self):
        self.assertEqual(self.reason("today show thanksgiving recipes 2025"), "media_brand_navigational")
        self.assertEqual(self.reason("good morning america thanksgiving"), "media_brand_navigational")
        self.assertEqual(self.reason("gma thanksgiving recipes today"), "media_brand_navigational")
        self.assertIsNone(self.reason("grandma gma thanksgiving shirt"))  # gma = grandma on a shirt

    def test_restaurants_and_grocery_chains(self):
        self.assertEqual(self.reason("harvest room thanksgiving menu"), "restaurant_grocery_navigational")
        self.assertEqual(self.reason("olive garden thanksgiving dinner"), "restaurant_grocery_navigational")
        self.assertIsNone(self.reason("thanksgiving dinner menu ideas"))
        self.assertIsNone(self.reason("restaurant thanksgiving menu ideas"))

    def test_school_calendars(self):
        self.assertEqual(self.reason("hillsborough county thanksgiving break 2025"), "school_calendar_navigational")
        self.assertEqual(self.reason("chicago public schools thanksgiving break"), "school_calendar_navigational")
        self.assertIsNone(self.reason("when is thanksgiving break"))
        self.assertIsNone(self.reason("do public schools have thanksgiving break"))

    def test_assistant_prefix_is_the_same_question(self):
        n = kw_text.normalize_text
        self.assertEqual(n("google when is thanksgiving"), "when is thanksgiving")
        self.assertEqual(n("Hey Siri, what day is Thanksgiving?"), "what day is thanksgiving")
        self.assertEqual(n("google thanksgiving"), "google thanksgiving")  # not a question: left alone


def kw(keyword, volume, fixed=False):
    k = ck.KW()
    k.keyword, k.volume, k.fixed = keyword, volume, fixed
    return k


class NaturalMainKeyword(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        phrases = ["true story of thanksgiving", "story of thanksgiving", "the story of thanksgiving for kids",
                   "true story of the pilgrims", "thanksgiving facts for kids", "thanksgiving games for kids",
                   "thanksgiving crafts for kids", "thanksgiving books for kids", "thanksgiving videos for kids",
                   "real story thanksgiving", "thanksgiving facts for kindergarteners"]
        cls.fl = Fluency(phrases * 3)

    def test_fluency_prefers_usual_word_pairs(self):
        self.assertGreater(self.fl.score("true story of thanksgiving"), self.fl.score("real story thanksgiving"))
        self.assertGreater(self.fl.score("thanksgiving facts for kids"), self.fl.score("thanksgiving facts for kindergarteners"))

    def test_a_clearly_more_natural_phrasing_names_the_post(self):
        cl = [kw("real story thanksgiving", 1600), kw("thanksgiving story true", 1600), kw("true story of thanksgiving", 1300)]
        self.assertEqual(ck.evergreen_seed(cl, self.fl)[0].keyword, "true story of thanksgiving")
        cl = [kw("thanksgiving facts for kindergarteners", 390), kw("thanksgiving facts for kids", 320)]
        self.assertEqual(ck.evergreen_seed(cl, self.fl)[0].keyword, "thanksgiving facts for kids")

    def test_volume_still_matters(self):
        cl = [kw("real story thanksgiving", 1600), kw("true story of thanksgiving", 1000)]  # 62%: too far below
        self.assertEqual(ck.evergreen_seed(cl, self.fl)[0].keyword, "real story thanksgiving")
        self.assertEqual(ck.evergreen_seed([kw("real story thanksgiving", 1600), kw("true story of thanksgiving", 1300)])[0].keyword,
                         "real story thanksgiving")  # no fluency model: the old rule

    def test_a_keyword_typed_with_a_typo_never_names_the_post(self):
        cl = [kw("thanks giving day", 300, fixed=True), kw("thanksgiving day", 200)]
        self.assertEqual(ck.evergreen_seed(cl, self.fl)[0].keyword, "thanksgiving day")


def row(cid, name, vol, core="", seed=None, theme="activities", kd=30, fl=-2.0):
    return {"cluster_id": cid, "cluster_name": name, "cluster_volume": str(vol), "seed_volume": str(seed or vol),
            "core": core, "seed_kd": str(kd), "blog_fit": "high", "reader_need": "inspire", "theme": theme,
            "name_fluency": str(fl), "keywords": name, "market": "us"}


class SubTopicPosts(unittest.TestCase):
    def kept_and_merged(self, members, **kw):
        hub = members[0]
        kept, merged = tm.select_posts(hub, members, kw.pop("max_posts", 6), kw.pop("min_post_volume", 300), **kw)
        return {r["cluster_name"] for r in kept}, {cid: t["cluster_name"] for cid, t in merged.items()}

    def test_a_long_tail_that_adds_up_becomes_one_post(self):
        members = [row("H", "thanksgiving activities", 9000)]
        members += [row("G1", "games to play at thanksgiving with family", 700, "family game", seed=400),
                    row("G2", "thanksgiving games for adults", 350, "adults game"),
                    row("G3", "thanksgiving games for the table", 260, "game table"),
                    row("G4", "thanksgiving games youth group", 300, "game group youth"),
                    row("G5", "easy games for thanksgiving", 200, "game", seed=40)]
        members += [row(f"X{i}", f"thanksgiving odd thing {w}", 120, w) for i, w in enumerate("abcdefgh")]
        kept, merged = self.kept_and_merged(members)
        self.assertEqual(kept, {"games to play at thanksgiving with family"})  # strongest name among the games
        for cid in ("G2", "G3", "G4", "G5"):
            self.assertEqual(merged[cid], "games to play at thanksgiving with family")
        self.assertEqual(merged["X0"], "thanksgiving activities")  # small one-offs stay sections of the hub

    def test_a_big_distinct_sub_topic_is_kept_next_to_a_huge_one(self):
        members = [row("H", "history of thanksgiving", 30000, theme="history"),
                   row("F", "when was the first thanksgiving", 50000, "first", theme="history"),
                   row("K", "thanksgiving story for kindergarten", 3000, "kids", theme="history"),
                   row("S", "thanksgiving history small", 900, "small", theme="history")]
        members += [row(f"X{i}", f"thanksgiving odd thing {w}", 100, w, theme="history") for i, w in enumerate("abcdefgh")]
        kept, _ = self.kept_and_merged(members)
        self.assertIn("thanksgiving story for kindergarten", kept)  # 3,000 >= keep_volume although < 10% of 50,000
        self.assertNotIn("thanksgiving history small", kept)  # 900 < 10% of the strongest sub-topic
        kept, _ = self.kept_and_merged(members, keep_volume=10000)
        self.assertNotIn("thanksgiving story for kindergarten", kept)

    def test_narrower_posts(self):
        members = [row("H", "history of thanksgiving", 30000, theme="history"),
                   row("F", "when was the first thanksgiving", 20000, "first", theme="history"),
                   row("FF", "what food was at the first thanksgiving", 3000, "first food", theme="history"),
                   row("FL", "how long did the first thanksgiving last", 900, "first long", theme="history"),
                   row("B", "thanksgiving books", 2500, "book", theme="history"),
                   row("BK", "thanksgiving books for kids", 2000, "book kids", theme="history")]
        members += [row(f"X{i}", f"thanksgiving odd thing {w}", 100, w, theme="history") for i, w in enumerate("abcdefgh")]
        kept, merged = self.kept_and_merged(members, max_posts=8)
        self.assertIn("what food was at the first thanksgiving", kept)  # a different subject: 15% of its parent
        self.assertEqual(merged["FL"], "when was the first thanksgiving")  # under 10% of its parent: a section
        self.assertEqual(merged["BK"], "thanksgiving books")  # only says who it is for: a section of 'books'

    def test_small_pillars_keep_every_cluster(self):
        members = [row("H", "thanksgiving activities", 900), row("A", "thanksgiving games", 50, "game")]
        self.assertEqual(self.kept_and_merged(members), ({"thanksgiving games"}, {}))

    def test_same_post_in_two_theme_pillars(self):
        big, small = row("T", "is thanksgiving always on a thursday", 40000, "thursday", theme="dates"), \
            row("M", "why do we celebrate thanksgiving on thursday", 470, "thursday", theme="meaning")
        k1, k2 = row("K1", "thanksgiving facts for kids", 1200, "kids", theme="facts"), \
            row("K2", "thanksgiving story for kids", 4000, "kids", theme="history")
        plans = [{"theme": "dates", "topic": "t", "kept": [big], "merged": {}, "members": [big]},
                 {"theme": "meaning", "topic": "t", "kept": [small, k1], "merged": {}, "members": [small, k1]},
                 {"theme": "history", "topic": "t", "kept": [k2], "merged": {}, "members": [k2]}]
        tm.dedupe_across_pillars(plans)
        self.assertEqual(plans[1]["kept"], [k1])  # who-only cores ({kids}) are different posts
        self.assertIs(plans[1]["merged"]["M"], big)

    def test_long_tail_without_a_theme_finds_its_pillar(self):
        names = row("N", "thanksgiving names", 670, "name", theme="")
        cands = [(row("A", "another name for thanksgiving", 1700, "name", theme="messages"), ("us", "occasion", "t/messages")),
                 (row("B", "thanksgiving speech", 1500, "speech", theme="messages"), ("us", "occasion", "t/messages2"))]
        self.assertEqual(tm.adopt(names, cands), ("us", "occasion", "t/messages"))
        self.assertIsNone(tm.adopt(row("Z", "thanksgiving festival", 790, "festival", theme=""), cands))
        self.assertIsNone(tm.adopt(row("K", "thanksgiving kids", 360, "kids", theme=""), cands))  # who-only: too vague


def post(cid, kw, slug, role="cluster", vol=1000):
    return {"pillar_id": "P01", "role": role, "cluster_id": cid, "primary_keyword": kw, "planned_slug": slug,
            "cluster_volume": str(vol), "priority_score": str(vol), "keywords": kw, "market": "us", "parent_hint": "",
            "merged_into": ""}


def kwr(cid, keyword, volume, kd=30, fixed=0):
    return {"cluster_id": cid, "keyword": keyword, "volume": str(volume), "kd": str(kd), "spelling_fixed": str(fixed),
            "variants": "", "variant_volumes": ""}


class SecondaryKeywords(unittest.TestCase):
    def test_rephrasings_are_capped_and_new_angles_fill_the_rest(self):
        topic = [post("C1", "when is thanksgiving", "when-is-thanksgiving", "pillar", 900000)]
        keywords = [kwr("C1", k, v) for k, v in [
            ("when is thanksgiving", 823000), ("what day is thanksgiving", 60500), ("when is thanksgiving this year", 30000),
            ("thanksgiving day", 27100), ("when is it thanksgiving", 20000), ("what date is thanksgiving", 15000),
            ("thanksgiving bank holiday 2025", 5000), ("how many days until thanksgiving", 4000),
            ("day after thanksgiving", 3000)]] + [kwr("C1", "thanksgivng day", 2000, fixed=1)]
        plan = ep.Plan(topic, keywords, None, "https://printerval.com/{slug}", 10, "main", 3, year=2026)
        listed, roles = plan.secondary(plan.posts[0])
        self.assertEqual(listed, ["what day is thanksgiving", "when is thanksgiving this year", "thanksgiving day",
                                  "how many days until thanksgiving", "day after thanksgiving"])
        role = {k["keyword"]: r for k, r in roles}
        self.assertEqual(role["what date is thanksgiving"], "also covers")  # a 4th rephrasing
        self.assertEqual(role["thanksgiving bank holiday 2025"], "also covers")  # a past year
        self.assertEqual(role["thanksgivng day"], "also covers")  # a typo


class PlanQA(unittest.TestCase):
    def test_overlap_misplaced_and_year(self):
        topic = [post("C1", "when is thanksgiving", "when-is-thanksgiving", "pillar", 900000),
                 post("C2", "is thanksgiving always on a thursday", "is-thanksgiving-always-on-a-thursday"),
                 post("C3", "thanksgiving 2025 date", "thanksgiving-date"),
                 post("C4", "is thanksgiving always thursday", "is-thanksgiving-always-thursday", vol=300)]
        keywords = [kwr("C1", "when is thanksgiving", 800000), kwr("C1", "thanksgiving thursday", 900),
                    kwr("C2", "is thanksgiving always on a thursday", 2900), kwr("C3", "thanksgiving 2025 date", 500),
                    kwr("C4", "is thanksgiving always thursday", 300, kd=75)]
        plan = ep.Plan(topic, keywords, None, "https://printerval.com/{slug}", 10, "main", 3, year=2026)
        rows = list(plan.rows())
        qa = ep.qa_rows(plan, rows)
        found = {(i[1], i[2]) for i in qa}
        self.assertIn(("overlap", 4), found)  # STT 4 asks what STT 2 asks
        self.assertIn(("misplaced", 1), found)  # 'thanksgiving thursday' is STT 2's question
        self.assertIn(("year_in_main", 3), found)
        self.assertIn(("weak_post", 4), found)
        self.assertIn(("hard_keyword", 4), found)
        self.assertNotIn(("overlap", 3), found)  # 'thanksgiving date' and 'when is thanksgiving' differ only by fillers
        self.assertEqual(qa[0][0], "high")  # most severe first
        self.assertIn("items to review", plan_qa.summary(qa))


if __name__ == "__main__":
    unittest.main()
