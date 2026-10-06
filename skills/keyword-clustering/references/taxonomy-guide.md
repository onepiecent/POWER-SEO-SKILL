# Extending the taxonomy, custom groups and noise rules

Three configurations can be changed without touching the code:

| Purpose | File | Use |
|---|---|---|
| Add a new niche/occasion/recipient/product to a facet | an extension JSON | `--extend-taxonomy file.json` (or edit `assets/taxonomy.json` directly) |
| Group in the brief's own way (Family, Pets, Work...) | `categories.json` | `--categories categories.json --group-by category` |
| Add or remove noise-exclusion rules | `assets/noise-rules.json` | `--noise-rules file.json` or `--no-noise-filter` |

## 1. Extending the taxonomy

Structure: `facets -> <facet> -> values -> <key> -> {label, patterns, seasonal?}`. Facets: `occasion`, `interest`, `recipient`, `product`, `style`, `craft`.

```json
{
  "facets": {
    "interest": {"values": {"pickleball": {"label": "Pickleball Players", "patterns": ["\\bpickleball\\w*\\b"]}}},
    "recipient": {"values": {"nurse": {"patterns": ["\\bnurse practitioners?\\b"]}}}
  }
}
```

- A **new key** is added; for an **existing key** the patterns are appended (and other fields such as the label are overwritten).
- A pattern is a **Python regex run on normalised text**: lowercase, apostrophes removed (`mother's` -> `mothers`), hyphens -> spaces (`t-shirt` -> `t shirt`). Always use the word boundary `\b` and remember plurals and variants (`fisherm[ae]n`, `anglers?`).
- `label` is used to name the pillar ("Gift Ideas for Pickleball Players"). For a recipient with a UK variant, add `label_uk` (for example Mum, Nan & Grandma).
- `"seasonal": true` is for an occasion with a specific date; then add a date rule to `editorial-calendar/scripts/occasion_calendar.py` (OCCASIONS), otherwise `seasonal-plan.csv` will report `no_calendar_rule`.
- Besides facets you can add `weak_tokens`, `variants` (UK->US, for matching), `phrase_variants`, `us_only_terms`, `uk_only_terms`, `blog_fit`, and `reader_need_rules_prepend` (need rules placed first).

**Suggested workflow when a file has many unclassified keywords:** open `taxonomy-suggestions.csv` (frequent n-grams among unrecognised keywords, sorted by volume), group the meaningful suggestions into niches/occasions, write an extension JSON, run again and compare the unclassified rate. For every new niche, check on a sample of real keywords that the regex does not match by mistake (for example "bird" in "bird watching" but not golf's "birdie").

**Matching order and "masking":** occasions and then interests are matched first, and the matched span is masked so later facets do not count it again ("dog mom" -> `interest=dogs`, `recipient=mom`; "mother's day" does not produce `recipient=mom`). "Gifts from daughter" does not count the daughter as the recipient.

### Themes (sub-topics of one topic)

`facets -> theme` splits one big topic (a single-occasion export) into sub-topics: dates, history, meaning, facts, printables, humor, crafts, decor, images, world, gifts, events, activities, food, messages. They work differently from the other facets:

- **Order matters**: the first theme whose `patterns` match wins (messages before facts before ... before dates), so "first thanksgiving food" is history, not food. `weak_patterns` (for example "celebrate", "ideas", "why") are only tried when no theme matched strongly. A keyword that names a product and nothing else is `product_theme` (gifts); an occasion keyword that only adds a year (`thanksgiving 2026`) or nothing (`thanksgiving`) is `year_only` (dates). Know-how keywords (craft facet) get no theme.
- `need`: the reader need used when the reader-need rules find nothing (dates/history -> info, messages -> copy_ideas...).
- `generic`: words that do not change the question within the theme; they are removed before comparing **cores** (`when is`, `what day`, `date`, `this year` for dates; `history`, `origin`, `how did it start` for history). Two clusters with the same core become one post.
- `fallback`: where a theme's posts go when topic-map splits a topic and the theme is too small to be a pillar (facts -> meaning, food -> activities, images -> messages).
- Top-level `core_stopwords` and `core_synonyms` (`true/truth/real -> real`, `pilgrims/1621/plymouth/original -> first`, `always/thursday/determined -> thursday`, `earliest/latest -> earliest`, `vacation/trip/destination -> travel`) complete the core; `phrase_variants` turns a phrase into one token before that (`places to visit -> travel`, `this or that -> thisorthat`, a game's name). Add a synonym when two phrasings of one question still end up in two posts. Cores also decide which sub-topics `topic-map` keeps as posts, so a synonym that is too broad merges posts (`place -> travel` would put "four places called Thanksgiving" in the travel post).

A facet value can also have `requires` (a regex): the value only applies when that regex matches too or a product is named. The know-how values sizing, care and materials use it, so "turkey size" or "dry turkey" are not apparel questions.

Extending a theme works like any facet: `{"facets": {"theme": {"values": {"food": {"patterns": ["\\bsheet pan\\b"]}}}}}` appends the pattern; lists (`patterns`, `weak_patterns`, `generic`) are appended, other fields replaced.

## 2. `categories.json` (custom groups)

```json
{
  "Pets": ["dog", "cat", "puppy", "kitten", "pet"],
  "Family & relationships": ["mom", "dad", "grandma", "family"],
  "Work & school": ["teacher", "nurse", "re:\\bback to school\\b"]
}
```

- Each term automatically gets word boundaries and plurals (`dog` matches `dogs`); the `re:` prefix uses a raw regex.
- A keyword goes into the **first group that matches, in file order**; no match = `(none)`. Put specific groups before broad ones.
- `--group-by category` needs this file. Groupings can be combined: `--group-by category,occasion`.
- `topic-map` understands `category` as a facet: `topic_map.py clusters.csv --priority category,occasion`.

## 3. Noise rules

`assets/noise-rules.json`: a list of `rules`, each with a `name` (shown in `excluded.csv`), `on` (`norm` or `raw`) and `patterns`. Defaults: navigational retailer/brand queries (including POD competitors and UK retailers), account/support/brand-reputation queries (login, scam, legit...), local intent (near me, `things to do on thanksgiving in dc` and other big cities), gift-card balance, adult content, Spanish (`cuando es`, `que dia es`, `thanksgiving en`...), other languages and translation queries, politics and news (`trump thanksgiving`), homework answer keys (CommonLit, Quizlet, "answer key"), opening hours (`is walmart open on thanksgiving`), TV shows and media brands (`today show thanksgiving recipes`, Good Morning America, Food Network; `gma` only next to recipes/deals, since on a shirt it means grandma), restaurant menus and restaurant/grocery chains (`harvest room thanksgiving menu`, Olive Garden; "menu ideas" stays), school-district and university calendars (`hillsborough county thanksgiving break`; "when is thanksgiving break" stays), Wikipedia, URLs/domains; plus a length limit (12 words / 120 characters) and a limit on the share of non-Latin characters. Language rules are checked on the original words, before spelling fixes.

Rule of thumb: a rule should only exclude what **certainly does not belong on a blog**; anything that is merely "a weaker fit" should be left to `blog_fit`. After editing a rule, re-read `excluded.csv` sorted by volume to make sure no large keyword was dropped by mistake.
