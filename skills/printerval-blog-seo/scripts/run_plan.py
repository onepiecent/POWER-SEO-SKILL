#!/usr/bin/env python3
"""Run the whole planning pipeline in one command: keyword export(s) -> final-plan.xlsx. Standard library only.

    run_plan.py export.xlsx --market us --only occasion=thanksgiving --out outputs \\
        [--published published-posts.xlsx] [--previous outputs/final-plan.xlsx] [--today 2026-10-06]
    run_plan.py [export.csv] --prior seo-grouped.xlsx::us --decisions decisions.csv --out outputs
    run_plan.py ... --serp serp.csv          # after checking the keywords of sheet SERP To-do on Google

--prior goes to step 1 with --prior-mode (audit, the default: the SEO's grouping is checked against the rules and
regrouped where one fails; keep: kept as it is) and --site-kd (the KD the site can rank for: winnable volume picks
main keywords, pillars and posts); --decisions to steps 1, 2 and 5 (each logs decisions-log-<step>.csv). Step 5 also
gets backcheck.csv, excluded.csv, seo-audit*.csv, serp-check.csv and this run's decision logs when they exist; the
last line counts the decisions. --serp (SERP data checked by hand: the keywords of sheet SERP To-do, looked up with
assets/serp-extract.js) goes to steps 1 and 5: shared top-10 URLs merge or keep apart, and sheet SERP Check shows
every verdict; --serp-budget sets how many keywords SERP To-do asks for (default 25).

Steps (each skill's own script, run as a separate process so every skill stays self-contained):
  1. keyword-clustering   cluster_keywords.py  -> clusters.csv, keyword-map.csv, cluster-report.md
  2. topic-map            topic_map.py         -> topic-map.csv/.md
  3. editorial-calendar   occasion_calendar.py -> seasonal-plan.csv
  4. internal-link-planner link_plan.py plan   -> link-plan.csv
  5. printerval-blog-seo  export_plan.py       -> final-plan.xlsx + .csv (Plan, Keyword Map, Schedule, QA, SEO Audit,
                                                  Link Plan, SERP To-do, SERP Check, Research Next, Published Match,
                                                  Changes, Review, Back-check, Decisions, Not Planned)
The skills are looked up next to this one (the repository and claude.ai's /mnt/skills/... share that layout), in
--skills-dir, or in ~/.claude/skills. Each step's summary is printed; read cluster-report.md and the QA sheet before
handing the plan over. Options that are not listed here go through --cluster-args / --topic-args / --export-args.
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import shlex
import subprocess
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOTS = [os.path.join(HERE, "..", ".."), "/mnt/skills/user", "/mnt/skills/public", "/mnt/skills",
               os.path.expanduser("~/.claude/skills")]


def find_script(skill: str, script: str, skills_dir: str | None) -> str:
    for root in ([skills_dir] if skills_dir else []) + SKILL_ROOTS:
        path = os.path.join(root, skill, "scripts", script)
        if os.path.exists(path):
            return os.path.abspath(path)
    raise SystemExit(f"Skill '{skill}' ({script}) not found next to printerval-blog-seo or in {SKILL_ROOTS[1:]}: "
                     "install it, or pass --skills-dir <folder that contains the skills>.")


def run(step: str, cmd: list[str]) -> None:
    print(f"== {step}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.strip() and not line.startswith(("Written", "Read cluster-report")):
            print("   " + line)
    if r.returncode != 0:
        print(r.stderr.strip(), file=sys.stderr)
        raise SystemExit(f"{step} failed (exit code {r.returncode}): {' '.join(shlex.quote(c) for c in cmd)}")
    for line in r.stderr.splitlines():
        if line.strip():
            print("   ! " + line)


def this_run_logs(o, before: dict[str, float]) -> list[str]:
    """decisions-log-*.csv files written (or rewritten) since the run started."""
    return [p for p in sorted(glob.glob(o("decisions-log-*.csv"))) if before.get(p) != os.path.getmtime(p)]


def decisions_summary(o, before: dict[str, float]) -> str:
    """One line from this run's back-check and decision logs; empty when there are none."""
    parts = []
    if os.path.exists(o("backcheck.csv")):
        with open(o("backcheck.csv"), encoding="utf-8-sig", newline="") as fh:
            issues = list(csv.DictReader(fh))
        sev = Counter(r.get("severity", "") for r in issues)
        proposals = 0
        if os.path.exists(o("proposed-decisions.csv")):
            with open(o("proposed-decisions.csv"), encoding="utf-8-sig", newline="") as fh:
                proposals = sum(1 for _ in csv.DictReader(fh))
        parts.append(f"Back-check: {len(issues)} issues (high {sev['high']}, medium {sev['medium']}), "
                     f"{proposals} proposals in proposed-decisions.csv")
    status: Counter = Counter()
    logs = this_run_logs(o, before)
    for p in logs:
        with open(p, encoding="utf-8-sig", newline="") as fh:
            status.update(r.get("status", "") for r in csv.DictReader(fh))
    if logs:
        parts.append(f"decisions: {status['applied'] + status['applied_with_warning']} applied "
                     f"({status['applied_with_warning']} with a warning), {status['already_true']} already true, "
                     f"{status['stale']} stale, {status['rejected_by_data']} rejected by data, "
                     f"{status['invalid']} invalid, {status['conflict']} conflict (" + ", ".join(os.path.basename(p) for p in logs) + ")")
    return "; ".join(parts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="keyword export(s), CSV or .xlsx; file.csv::uk assigns a market "
                                             "(optional with --prior)")
    ap.add_argument("--prior", action="append", help="a file the SEO already grouped, FILE[::market] (repeatable): "
                                                     "back-checked and supplemented by the exports")
    ap.add_argument("--prior-mode", choices=["audit", "keep"], help="audit (default) or keep the SEO's groups")
    ap.add_argument("--site-kd", type=float, help="the KD the site can rank for (default: measured from ranking "
                                                  "positions in the exports, else 30)")
    ap.add_argument("--decisions", help="decisions file (CSV, or .xlsx sheet Decisions) applied by the cluster, topic "
                                        "and export steps; each step logs them in decisions-log-<step>.csv")
    ap.add_argument("--serp", action="append", help="SERP data checked by hand or exported (serp.csv: keyword, url, "
                                                    "market, position...), repeatable: steps 1 and 5")
    ap.add_argument("--serp-budget", type=int, help="keywords in sheet SERP To-do (default 25; 0: no sheet)")
    ap.add_argument("--posts", type=int, help="only when the SEO asks for N posts: the N with the highest priority are "
                                             "planned, the rest go to the backlog (default: the data decides)")
    ap.add_argument("--out", default="outputs", help="output folder (default outputs)")
    ap.add_argument("--market", help="default market for files without a country column (us|uk)")
    ap.add_argument("--only", action="append", help="keep one topic, e.g. occasion=thanksgiving (repeatable)")
    ap.add_argument("--include", action="append", help="keep only keywords matching this regex (repeatable)")
    ap.add_argument("--exclude", action="append", help="drop keywords matching this regex (repeatable)")
    ap.add_argument("--min-volume", type=int)
    ap.add_argument("--published", help="CSV/.xlsx of the blog posts already published (URL + Title)")
    ap.add_argument("--previous", help="a previous final-plan.xlsx the team already works in")
    ap.add_argument("--today", help="YYYY-MM-DD for deadlines (default: today)")
    ap.add_argument("--year", type=int, help="plan year for the secondary keywords (default: this year)")
    ap.add_argument("--url-pattern", help="planned URL pattern, default https://printerval.com/{slug}")
    ap.add_argument("--plan-name", default="final-plan.xlsx", help="file name of the final plan (default final-plan.xlsx)")
    ap.add_argument("--cluster-args", default="", help="extra options for cluster_keywords.py, e.g. \"--granularity loose\"")
    ap.add_argument("--topic-args", default="", help="extra options for topic_map.py, e.g. \"--max-posts 15\"")
    ap.add_argument("--export-args", default="", help="extra options for export_plan.py, e.g. \"--max-secondary 8\"")
    ap.add_argument("--skills-dir", help="folder that contains the skill folders, when they are not next to this one")
    args = ap.parse_args(argv)
    if not args.files and not args.prior:
        ap.error("give at least one keyword export or --prior FILE")

    py, out = sys.executable, os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    o = lambda name: os.path.join(out, name)  # noqa: E731
    decisions = ["--decisions", os.path.abspath(args.decisions)] if args.decisions else []
    logs_before = {p: os.path.getmtime(p) for p in glob.glob(o("decisions-log-*.csv"))}
    cluster = [py, find_script("keyword-clustering", "cluster_keywords.py", args.skills_dir), *args.files, "--out", out]
    for p in args.prior or []:
        cluster += ["--prior", p]
    if args.market:
        cluster += ["--market", args.market]
    for flag, values in (("--only", args.only), ("--include", args.include), ("--exclude", args.exclude)):
        for v in values or []:
            cluster += [flag, v]
    if args.min_volume is not None:
        cluster += ["--min-volume", str(args.min_volume)]
    if args.prior_mode:
        cluster += ["--prior-mode", args.prior_mode]
    if args.site_kd is not None:
        cluster += ["--site-kd", str(args.site_kd)]
    serp = []
    for p in args.serp or []:
        serp += ["--serp", os.path.abspath(p)]
    cluster += serp
    run("1/5 keyword-clustering", cluster + decisions + shlex.split(args.cluster_args))
    run("2/5 topic-map", [py, find_script("topic-map", "topic_map.py", args.skills_dir), o("clusters.csv"), "--out", out]
        + (["--posts", str(args.posts)] if args.posts else []) + decisions + shlex.split(args.topic_args))
    calendar = [py, find_script("editorial-calendar", "occasion_calendar.py", args.skills_dir),
                "--topic-map", o("topic-map.csv"), "--out", out]
    run("3/5 editorial-calendar", calendar + (["--today", args.today] if args.today else []))
    run("4/5 internal-link-planner", [py, find_script("internal-link-planner", "link_plan.py", args.skills_dir), "plan",
                                      o("topic-map.csv"), "--out", out])
    plan = o(args.plan_name if args.plan_name.endswith(".xlsx") else args.plan_name + ".xlsx")
    export = [py, os.path.join(HERE, "export_plan.py"), "--topic-map", o("topic-map.csv"), "--keyword-map",
              o("keyword-map.csv"), "--link-plan", o("link-plan.csv"), "--seasonal-plan", o("seasonal-plan.csv"),
              "--out", plan]
    for flag, value in (("--published", args.published), ("--previous", args.previous), ("--today", args.today),
                        ("--year", args.year), ("--url-pattern", args.url_pattern)):
        if value:
            export += [flag, str(value)]
    export += serp + (["--serp-budget", str(args.serp_budget)] if args.serp_budget is not None else [])
    for flag, name in (("--backcheck", "backcheck.csv"), ("--excluded", "excluded.csv"),
                       ("--seo-audit", "seo-audit.csv"), ("--seo-audit", "seo-audit-topic.csv"),
                       ("--serp-check", "serp-check.csv")):
        if os.path.exists(o(name)):
            export += [flag, o(name)]
    for log in this_run_logs(o, logs_before):  # the cluster and topic logs (an earlier run's are left out)
        export += ["--decision-log", log]
    run("5/5 final plan", export + decisions + shlex.split(args.export_args))
    summary = decisions_summary(o, logs_before)
    if summary:
        print("\n" + summary)
    print(f"\nDone. Read {o('cluster-report.md')} first (input, filters, spelling fixes), then the QA sheet of {plan}.")
    print(f"Final plan: {plan} (+ .csv). Other files in {out}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
