#!/usr/bin/env python3
"""Run the whole planning pipeline in one command: keyword export(s) -> final-plan.xlsx. Standard library only.

    run_plan.py export.xlsx --market us --only occasion=thanksgiving --out outputs \\
        [--published published-posts.xlsx] [--previous outputs/final-plan.xlsx] [--today 2026-10-06]

Steps (each skill's own script, run as a separate process so every skill stays self-contained):
  1. keyword-clustering   cluster_keywords.py  -> clusters.csv, keyword-map.csv, cluster-report.md
  2. topic-map            topic_map.py         -> topic-map.csv/.md
  3. editorial-calendar   occasion_calendar.py -> seasonal-plan.csv
  4. internal-link-planner link_plan.py plan   -> link-plan.csv
  5. printerval-blog-seo  export_plan.py       -> final-plan.xlsx + .csv (Plan, Keyword Map, Schedule, QA, Research
                                                  Next, Published Match, Changes)
The skills are looked up next to this one (the repository and claude.ai's /mnt/skills/... share that layout), in
--skills-dir, or in ~/.claude/skills. Each step's summary is printed; read cluster-report.md and the QA sheet before
handing the plan over. Options that are not listed here go through --cluster-args / --topic-args / --export-args.
"""
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys

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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="keyword export(s), CSV or .xlsx; file.csv::uk assigns a market")
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

    py, out = sys.executable, os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    o = lambda name: os.path.join(out, name)  # noqa: E731
    cluster = [py, find_script("keyword-clustering", "cluster_keywords.py", args.skills_dir), *args.files, "--out", out]
    if args.market:
        cluster += ["--market", args.market]
    for flag, values in (("--only", args.only), ("--include", args.include), ("--exclude", args.exclude)):
        for v in values or []:
            cluster += [flag, v]
    if args.min_volume is not None:
        cluster += ["--min-volume", str(args.min_volume)]
    run("1/5 keyword-clustering", cluster + shlex.split(args.cluster_args))
    run("2/5 topic-map", [py, find_script("topic-map", "topic_map.py", args.skills_dir), o("clusters.csv"), "--out", out]
        + shlex.split(args.topic_args))
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
    run("5/5 final plan", export + shlex.split(args.export_args))
    print(f"\nDone. Read {o('cluster-report.md')} first (input, filters, spelling fixes), then the QA sheet of {plan}.")
    print(f"Final plan: {plan} (+ .csv). Other files in {out}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
