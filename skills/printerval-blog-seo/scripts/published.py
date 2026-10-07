#!/usr/bin/env python3
"""Match the planned posts with the blog posts already published (the content team's list). Standard library only.

The list needs a URL column and a title column (any CSV/.xlsx; Category and a focus keyword column are used when
present). Each published post is described by the words of its slug (the URL without '-n123.html') and of the main
part of its title (before '?', ':', '|' or ' - '): 'When Is Thanksgiving In 2024? The wonderful facts...' asks
'when is thanksgiving'.

  * same     the published post answers the planned post's main question (question words aside: 'history of
             thanksgiving' = 'when did thanksgiving begin') or one of its secondary keywords: update that post (its
             URL becomes URL Blog) instead of writing a new one
  * part     it answers one of the long-tail keywords merged into the planned post: link to it, do not repeat it
  * related  it shares a subject word with the planned post (a gift guide 'thanksgiving t-shirts for family' for
             'thanksgiving day family activities'): a natural Related Post that is already live
Duplicates among the published posts of the topic (same slug, another id) are listed too: they compete with each other.
All of this is a heuristic on words [Convention]; a person confirms each 'same' before the team updates a post.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from urllib.parse import urlparse

from table_io import column, read_table

HERE = os.path.dirname(os.path.abspath(__file__))
IP_WATCHLIST = os.path.join(HERE, "..", "..", "claims-compliance-check", "assets", "ip-watchlist.txt")

URL_NAMES = ["url", "link", "permalink", "address", "post url", "url blog", "đường dẫn"]
TITLE_NAMES = ["title", "post title", "tiêu đề", "h1", "name", "tên bài"]
CATEGORY_NAMES = ["category", "categories", "danh mục", "chuyên mục"]
KEYWORD_NAMES = ["focus keyword", "main keyword", "keyword", "từ khóa", "từ khoá"]
ID_SUFFIX_RX = re.compile(r"-n\d+$")
TITLE_CUT_RX = re.compile(r"\s*(?:[?:|!]| [-–—] ).*$")
LIST_START_RX = re.compile(r"^(?:top\s+)?\d+\+?\s+|^(?:discover|the best|best)\s+(?:\d+\+?\s+)?", re.I)
SAME, PART = 0.75, 0.75
FILLER = {"the", "a", "an", "of", "in", "on", "for", "to", "is", "are", "was", "were", "do", "does", "did", "and",
          "this", "that", "it", "its", "be", "will", "can", "should", "would", "there", "we", "you", "your", "our",
          "my", "me", "us", "with", "at", "from", "by", "or", "as", "really", "day", "happy", "about", "printerval"}
# one word for one idea when comparing a planned post with a published title ('when did thanksgiving begin' asks
# about the history of thanksgiving)
SYNONYMS = {"history": "origin", "historical": "origin", "origins": "origin", "originate": "origin",
            "originated": "origin", "begin": "origin", "began": "origin", "beginning": "origin", "start": "origin",
            "started": "origin", "starts": "origin", "true": "real", "truth": "real", "mean": "meaning",
            "means": "meaning"}
# words too common to make two posts related ('celebrate' is in half of the titles)
QUESTION_WORDS = {"when", "what", "why", "how", "who", "where", "which"}
RELATED_STOP = {"when", "what", "why", "how", "who", "where", "which", "celebrate", "celebration", "celebrating",
                "best", "top", "holiday", "fun", "cute", "great", "special", "simple", "fact", "idea", "thing", "way",
                "good", "new", "year", "date", "time", "week", "festive", "cozy", "love", "show", "perfect"}


def words(text: str) -> frozenset:
    out = set()
    for t in re.findall(r"[a-z0-9]+", text.lower().replace("'", "").replace("’", "")):
        if t in FILLER or re.fullmatch(r"(19|20)\d\d", t) or len(t) == 1:
            continue
        t = SYNONYMS.get(t, t)
        out.add(t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith(("ss", "us", "is", "ys")) else t)
    return frozenset(out)


def load_watchlist(path: str = IP_WATCHLIST) -> list[re.Pattern]:
    """Brand / franchise names from claims-compliance-check (when installed): a published post that names one is not
    suggested as a link before someone checks the IP risk."""
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("re:"):
                out.append(re.compile(line[3:], re.I))
            else:
                name = re.sub(r"['’\-]", " ", line.lower())
                out.append(re.compile(r"\b" + r"\s*".join(re.escape(w) for w in name.split()) + r"\b", re.I))
    return out


def jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def title_main(title: str) -> str:
    return TITLE_CUT_RX.sub("", title.strip())


def anchor_from_title(title: str) -> str:
    """'Top 21 Thanksgiving T-Shirts for Family to Enhance Your Holiday Spirit' -> 'thanksgiving t-shirts for family'."""
    full = LIST_START_RX.sub("", title_main(title)).strip()
    t = re.split(r"\s+(?:to|that|showing|with|from|you|your|for a|for an|for the|for your)\s+", full, maxsplit=1,
                 flags=re.I)[0]
    if len(t.split()) < 2:  # '50+ Quotes To Write Into Gift Card For Thanksgiving': 'quotes' alone describes nothing
        t = full
    return " ".join(t.split()[:8]).lower()


class Published:
    def __init__(self, rows: list[dict], watchlist: list[re.Pattern] | None = None):
        self.posts = []
        watchlist = load_watchlist() if watchlist is None else watchlist
        for r in rows:
            url = column(r, URL_NAMES)
            if not url.startswith("http"):
                continue
            title = column(r, TITLE_NAMES)
            slug = re.sub(r"\.(html?|php)$", "", [p for p in urlparse(url).path.split("/") if p][-1] if urlparse(url).path.strip("/") else "")
            base = ID_SUFFIX_RX.sub("", slug)
            plain = re.sub(r"['’\-]", " ", title.lower())
            ip = next((rx.pattern for rx in watchlist if rx.search(plain) or rx.search(base.replace("-", " "))), "")
            self.posts.append({"url": url, "title": title, "category": column(r, CATEGORY_NAMES),
                               "keyword": column(r, KEYWORD_NAMES), "slug_base": base,
                               "slug": words(base.replace("-", " ")), "main": words(title_main(title)),
                               "all": words(title) | words(base.replace("-", " ")), "ip": bool(ip)})

    @classmethod
    def load(cls, path: str) -> "Published":
        return cls(read_table(path, set(URL_NAMES)))

    def asks(self, q: dict) -> list[frozenset]:
        """What the published post answers: its slug, the main part of its title and its focus keyword."""
        return [s for s in (q["slug"], q["main"], words(q["keyword"]) if q["keyword"] else frozenset()) if s]

    def match(self, rows: list[dict], max_related: int = 2) -> dict[int, dict]:
        """rows: the plan rows (n, post, roles...). Returns {STT: {'same': [...], 'part': [...], 'related': [...]}}
        with items (score, published post, matching keyword)."""
        mains = [words(r["post"]["primary_keyword"]) for r in rows]
        share: dict[str, int] = defaultdict(int)
        for m in mains:
            for t in m:
                share[t] += 1
        topic = {t for t, n in share.items() if n >= max(3, 0.5 * len(rows))}  # 'thanksgiving'
        index: dict[str, list[dict]] = defaultdict(list)
        for q in self.posts:
            if not topic or q["all"] & topic:  # a one-topic plan only looks at published posts of that topic
                for t in q["all"] - topic:
                    index[t].append(q)
        best_same: dict[str, tuple] = {}
        out: dict[int, dict] = {r["n"]: {"same": [], "part": [], "related": []} for r in rows}
        rank = {"main": 2, "secondary": 1}
        for r in rows:
            n = r["n"]
            others = sorted(((k, role) for k, role in r["roles"] if role in ("also covers", "variant")),
                            key=lambda kr: -int(float(kr[0].get("volume") or 0)))[:40]
            keys = [(r["post"]["primary_keyword"], "main")] + [(k["keyword"], role) for k, role in r["roles"]
                                                                if role == "secondary"] + [(k["keyword"], role) for k, role in others]
            kw_words = [(words(k), k, role) for k, role in keys]
            main_words = words(r["post"]["primary_keyword"])
            main_subject = main_words - QUESTION_WORDS  # 'history of thanksgiving' = 'when did thanksgiving begin'
            mine = main_words - topic - RELATED_STOP
            seen, cands = set(), []
            for w, _, _ in kw_words:
                for t in w - topic:
                    for q in index.get(t, ()):
                        if id(q) not in seen:
                            seen.add(id(q))
                            cands.append(q)
            for q in cands:
                asks = self.asks(q)
                score, role_rank, kw = max(((max(jaccard(w, a) for a in asks), rank.get(rl, 0), k)
                                            for w, k, rl in kw_words if w), default=(0.0, 0, ""))
                close_to_main = max(jaccard(main_words, a) for a in asks) >= 0.5
                if main_subject - topic and max(jaccard(main_subject, a - QUESTION_WORDS) for a in asks) >= SAME:
                    score, role_rank, kw = max((score, role_rank, kw), (1.0, 2, r["post"]["primary_keyword"]))
                if score >= SAME and (role_rank or close_to_main):
                    out[n]["same"].append((score, q, kw))
                    key = (score, role_rank, close_to_main)
                    if q["url"] not in best_same or key > best_same[q["url"]][0]:
                        best_same[q["url"]] = (key, n)
                elif score >= PART:
                    out[n]["part"].append((score, q, kw))
                elif mine and not q["ip"]:
                    shared = mine & ((q["slug"] | q["main"]) - topic)
                    if shared:
                        out[n]["related"].append((len(shared) / len(mine), q, ", ".join(sorted(shared))))
        for n, m in out.items():  # a published post is the 'same' post of one planned post only (the best one)
            keep = [x for x in m["same"] if best_same.get(x[1]["url"], (None, n))[1] == n]
            m["part"] += [x for x in m["same"] if x not in keep]
            m["same"] = sorted(keep, key=lambda x: -x[0])
            m["part"].sort(key=lambda x: -x[0])
            m["related"] = sorted(m["related"], key=lambda x: -x[0])[:max_related]
        return out

    def duplicates(self, topic_words: set[str]) -> list[list[dict]]:
        """Published posts of the topic that share a slug (another id): they compete for the same query."""
        groups: dict[str, list[dict]] = defaultdict(list)
        for q in self.posts:
            if not topic_words or q["all"] & topic_words:
                groups[q["slug_base"]].append(q)
        return [g for g in groups.values() if len(g) > 1]
