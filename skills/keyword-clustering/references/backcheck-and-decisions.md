# Back-check and decisions: how a grouping is checked, decided and logged

The scripts compute and show evidence. Claude or the SEO makes the judgment calls in a **decisions file**, each with a reason and the evidence used. The scripts apply the decisions deterministically on every re-run and log every one, including the stale, rejected and conflicting ones. When nobody reviews, the heuristic default still runs and is labelled as such (`grouping_basis`, issues left `open`).

## Evidence hierarchy (strongest first)

1. SERP overlap from the export (`serp_urls`): the most direct evidence that two queries are served by the same pages. **[Convention]** (vendor docs disagree on the threshold: Keyword Insights, Serpstat, SE Ranking, LowFruits; no study validates one). The threshold is `--serp-overlap`.
2. The tool's own SERP-based grouping: Ahrefs Parent Topic/Keyword, Semrush Keyword Strategy Builder Page. **[Convention]** (vendor docs)
3. Co-ranking: one competitor URL ranks for both keywords (`ranking_url`), used as review evidence only.
4. Tool intent and SERP features: a hint, not proof; least reliable on ambiguous and low-volume keywords. **[Convention]** (vendor docs: Semrush intent is a machine-learning label)
5. Monthly data (Trend, Keyword Planner months).
6. Word, core and facet similarity: an internal heuristic (`--sim`).
7. Claude's reading of the meaning, stated as judgment and "not verified by SERP".

A web search is **not** a Google SERP: never record overlap counts from it. A decision that rests only on levels 6–7 says "not verified by SERP" in `evidence`, and the pair goes to the SEO through `serp-check.csv`.

Merge rule **[Google]**: one post per SERP-and-intent pair. Google's site-diversity system generally shows no more than two results per site, and the doorway and scaled-content-abuse policies forbid near-duplicate pages per variant. Keeping two close variants apart needs SERP evidence that they differ and a stated angle for each. Pillar/cluster is a **[Convention]**, not a Google concept.

## The SEO audit (`--prior`, `--prior-mode audit`, the default)

Before the back-check, a grouped input is audited against the skill's own rules (`kw_audit.py`, then `topic_map.py`) and **regrouped where a rule fails, on positive evidence only**; every change is a row of `seo-audit.csv` / `seo-audit-topic.csv` (sheet SEO Audit of the final plan). The rules, strongest evidence first: the same query in two groups (same normalised words, or SERP overlap of the mains) is one post; a keyword listed in several groups stays where it is the main, else where its words fit best; a pure shopping keyword leaves a blog group; a better main keyword (a year-free form, 2x the volume, or 1.25x the winnable volume while the SEO's main is above the site's KD reach; same subject words in the same order, never an inverted phrasing); a post that shares no subject word with its pillar but does with another moves there; a group at least as broad as the SEO's pillar that wins 1.5x its traffic becomes the hub; two groups that ask the same thing once angle words are set aside are one post; a group under `--seo-min-post-volume` (100) becomes a section of the closest post. A pair the words only suggest (`possible_duplicate`) is **not applied**: it goes to the SEO for a SERP check. Word similarity alone never splits an SEO group. `--prior-mode keep` skips the audit and keeps every group as it is. All thresholds are **[Convention]**.

## The back-check (`backcheck.csv`, every run)

`cluster_keywords.py` back-checks the groups in every run: the clusters as planned (one group per cluster, named after its SEO group when it has one), so a keyword the audit or a decision moved is checked where it is now. Every issue cites the real numbers from the data and proposes one decision; **nothing proposed is applied**. Thresholds: SERP overlap = `--serp-overlap`, word overlap = `--sim`; the other numbers are **[Convention]** and printed in `backcheck-report.md`.

| check | detects | proposed action |
|---|---|---|
| `duplicate_across_groups` | the same keyword in two or more groups (two posts would target it) | `move_keyword` |
| `secondary_is_other_main` | a secondary keyword of a group is, or answers the same query as, another group's main | `merge` |
| `same_question_groups` | two group mains answered by the same results (SERP overlap, same Parent Topic) | `merge` |
| `weak_member` | a member fits another group's main better than its own main: by SERP overlap (high, `move_keyword`), or, for an SEO group, by words only (low, no proposal: check both SERPs; never a keyword bigger than the target group, never a head term moved under a longer phrase that contains it; the engine's own clusters are not re-judged on words) | `move_keyword` (SERP only) |
| `mixed_intent` | the tool's intent labels split a group between readers who research and readers who buy (the smaller side ≥ 20% of the volume) | `split` |
| `ungrouped_high_volume` | export keywords in no SEO group form a cluster as big as the median SEO group main of the market (default: stays a new post) | none (default applied) |
| `main_not_best` | a member has at least 2× the main keyword's volume | `rename_main` (none when the engine chose the main on purpose: a more natural, evergreen or easier phrasing) |
| `no_data` | no keyword of the group has search volume in the exports | `research_seed` |
| `need_conflict` | the words say shop, the tool or the SERP says the reader researches (default: stays in the blog) | `set_need` |

Severity ∈ `high` (SERP or Parent Topic evidence, or the same keyword twice), `medium`, `low`, `info`.

## Actions by step (contract C2)

A step ignores, and does not log, actions meant for another step.

| step (script) | action | keyword / target / value |
|---|---|---|
| cluster (`cluster_keywords.py`) | `drop_keyword`, `keep_keyword` | keyword |
| | `set_need` | keyword; value = a reader need (inspire, choose, how_to, solve, copy_ideas, info, shop) |
| | `merge` | keyword = a member of the surviving post, target = a member of the absorbed post |
| | `move_keyword` | keyword goes to the post containing target |
| | `split` | keyword = the new main, value = `a|b|c` members that go with it |
| | `keep_apart` | keyword and target end in different posts |
| | `rename_main` | keyword becomes its post's main |
| topic (`topic_map.py`) | `set_pillar` | keyword = post main, target = pillar main or `none` |
| | `promote_pillar`, `demote_pillar`, `restore_backlog`, `drop_post` | keyword = the cluster or post main; value = reason for `drop_post` (for example `off-audience`) |
| export (`export_plan.py`) | `set_category`, `set_title`, `set_meta`, `set_outline` | keyword = Main Keyword or `STT:<n>`; value = the text (fills an empty team cell; a team value wins) |
| | `set_angle` | value = one line: the reader need served and Printerval's angle (Review sheet, "Angle (reviewed)") |
| | `research_seed` | value = seed keyword(s) to export; never a Plan row |

## The contradiction rule (contract C3)

- A **claude**-authored `merge`, `move_keyword`, `keep_apart` or `split` contradicted by the data is `rejected_by_data` and not applied. Contradicted means: both sides have SERP URLs and the overlap is below `--serp-overlap` (for `merge`/`move_keyword`), or at or above it (for `keep_apart`/`split`), or the Parent Topics differ (for `merge`/`move_keyword`). Do not retry it: tell the user and ask the SEO to check the live SERP.
- A **human**-authored one (any other `author`) is `applied_with_warning`: the SEO may have checked the live SERP. The warning stays in the log.
- A keyword not found is `stale`; `detail` names the closest current keyword by shared words, so the decision can be re-keyed.
- A row whose `author` is `proposal` (copied as it is from `proposed-decisions.csv`) is `invalid` in every step: a proposal is never applied until someone writes their own reason, evidence and name.
- Two decisions with opposite effects on the same pair (for example `merge A B` and `keep_apart A B`) are both `conflict`; neither is applied.
- An empty `reason` or `evidence` makes a decision `invalid`.

## File formats

**C1: the decisions file** (`decisions.csv`, or an `.xlsx` whose sheet `Decisions`, else the first sheet, has these headers):
`decision_id, action, market, keyword, target, value, reason, evidence, source_issue, author, date`

- `reason` and `evidence` are required; `evidence` quotes the numbers from the files (the `issue_id`, volumes, overlap counts, Parent Topic, intent labels, SERP features).
- `author`: `claude`, or anything else for a human (for example `seo:lan`).
- Keyword matching key (each skill implements `decision_key(text)` itself): Unicode NFC, lowercase, curly quotes made straight, apostrophes removed, `-` and `_` turned into spaces, whitespace collapsed. A keyword may be written `STT:<n>` for export actions.

**C3: the decision logs**, one per step: `decisions-log-cluster.csv`, `decisions-log-topic.csv`, `decisions-log-export.csv`:
`decision_id, step, action, market, keyword, target, value, author, status, detail`
with `status` ∈ `applied`, `applied_with_warning`, `already_true`, `rejected_by_data`, `stale`, `invalid`, `conflict`.

**C4: the back-check output** of keyword-clustering:

- `backcheck.csv`: `issue_id, check, severity, market, group, group_main, keyword, keyword_volume, other_group, other_main, evidence_type, evidence, proposed_action, proposed_keyword, proposed_target, proposed_value, status`. `issue_id` = `BC-` + the first 8 hex characters of sha1(`check|market|decision_key(keyword)|decision_key(other_main)`), stable across re-runs. `status` ∈ `open`, `applied_default`, `decided:<decision_id>`. `evidence` is a sentence with the real numbers.
- `proposed-decisions.csv`: the C1 columns, `decision_id` = `P-` + issue_id, `author` = `proposal`, `reason` = what the check found, `evidence` = the evidence sentence, `source_issue` = the issue_id. Copy an accepted row into the decisions file (keep or change its id, set `author`); proposals are never applied as they are.
- `backcheck-report.md`: counts by check and severity, then the issues by group.

The final plan shows all of this: the **Back-check** sheet (status updated from the logs), the **Decisions** sheet (every log row with its reason and evidence) and, per post, **Open Issues** and **Decisions Applied** in the **Review** sheet (`printerval-blog-seo/references/data-contracts.md`).
