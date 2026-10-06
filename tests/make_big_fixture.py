#!/usr/bin/env python3
"""Generate a large synthetic CSV to test clustering performance (fake data, not for SEO decisions).

Usage:  python3 tests/make_big_fixture.py 150000 /tmp/big.csv
"""
import csv
import random
import sys

OCC = ["mother's day", "father's day", "christmas", "halloween", "valentine's day", "birthday", "graduation",
       "thanksgiving", "easter", "wedding", "anniversary", "retirement", "baby shower", "housewarming"]
REC = ["mom", "dad", "grandma", "grandpa", "wife", "husband", "girlfriend", "boyfriend", "sister", "brother",
       "daughter", "son", "teacher", "nurse", "coworker", "friend", "couple", "kids", "teens", "boss"]
INT = ["dogs", "cats", "fishing", "camping", "hiking", "golf", "gaming", "music", "books", "gardening", "cooking",
       "yoga", "travel", "coffee", "wine", "football", "baseball", "horses", "crochet", "hunting", "cars", "faith"]
PROD = ["t shirt", "hoodie", "mug", "tumbler", "tote bag", "canvas", "blanket", "pillow", "hat", "socks"]
CARE = ["wash", "iron", "fix", "size", "remove stains from", "dry"]
MODS = ["ideas", "cheap", "unique", "cute", "online", "2026", "for her", "for him", "under 25", "under 50", "last minute",
        "diy", "handmade", "vintage", "modern", "classic", "luxury", "budget", "small", "large", "xl", "black", "white",
        "blue", "pink", "green", "red", "gold", "silver", "soft", "warm", "cozy", "heavy", "light", "organic", "cotton",
        "fast", "custom", "family", "group", "bulk", "set", "pack", "matching", "funny", "sweet", "simple", "creative",
        "thoughtful", "practical", "useful", "premium", "affordable", "trending", "popular", "top rated", "new", "usa"]
TEMPL = [
    "{occ} gifts for {rec}", "best {occ} gifts for {rec}", "{occ} gift ideas for {rec} who loves {int}",
    "{int} gifts for {rec}", "personalized {prod} for {rec}", "{occ} {prod} ideas", "how to {care} a {prod}",
    "{rec} {int} gift ideas {year}", "funny {int} {prod} slogans", "what to write in a {occ} card for {rec}",
    "{int} lover gift ideas", "{occ} gifts for {rec} {year}", "unique {int} gifts", "cheap {prod} for {int} lovers",
    "{rec} {occ} quotes", "gift ideas for {rec} who love {int}", "{occ} {int} gifts", "best {int} {prod}",
    "{int} {prod} vs {prod2}", "amazon {int} gifts", "{int} gifts near me", "regalos para {rec}",
]


def main(n: int, path: str) -> None:
    rng = random.Random(42)
    seen = set()
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["keyword", "volume", "kd", "market"])
        while len(seen) < n:
            t = rng.choice(TEMPL)
            kw = t.format(occ=rng.choice(OCC), rec=rng.choice(REC), int=rng.choice(INT), prod=rng.choice(PROD),
                          prod2=rng.choice(PROD), care=rng.choice(CARE), year=rng.choice(["2025", "2026", "2027"]))
            for _ in range(rng.choice([0, 0, 1, 1, 2])):
                kw += " " + rng.choice(MODS)
            if kw in seen:
                continue
            seen.add(kw)
            w.writerow([kw, int(rng.paretovariate(1.1) * 10), rng.randint(5, 80), "us"])


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2])
