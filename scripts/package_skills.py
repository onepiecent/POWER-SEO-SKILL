#!/usr/bin/env python3
"""Package each skill as a zip (to upload to claude.ai) or install the skills into a Claude Code skills folder.

    python3 scripts/package_skills.py                      # creates dist/<skill>.zip
    python3 scripts/package_skills.py --install ~/.claude/skills   # copy the skills into the target folder
    python3 scripts/package_skills.py --skills keyword-clustering topic-map

Each skill is self-contained: the zip holds a <skill>/ folder with SKILL.md at its root. __pycache__ and *.pyc are skipped.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SKILLS = os.path.join(ROOT, "skills")


def skill_dirs(names):
    all_names = sorted(d for d in os.listdir(SKILLS) if os.path.isfile(os.path.join(SKILLS, d, "SKILL.md")))
    if not names:
        return all_names
    missing = sorted(set(names) - set(all_names))
    if missing:
        raise SystemExit("No such skill: " + ", ".join(missing))
    return [n for n in all_names if n in names]


def iter_files(skill):
    base = os.path.join(SKILLS, skill)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for f in sorted(filenames):
            if not f.endswith(".pyc"):
                full = os.path.join(dirpath, f)
                yield full, os.path.join(skill, os.path.relpath(full, base))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skills", nargs="*", help="package only these skills")
    ap.add_argument("--install", metavar="DIR", help="copy the skills into DIR instead of creating zips")
    ap.add_argument("--dist", default=os.path.join(ROOT, "dist"))
    args = ap.parse_args(argv)
    names = skill_dirs(args.skills)
    if args.install:
        dest_root = os.path.expanduser(args.install)
        for name in names:
            dest = os.path.join(dest_root, name)
            if os.path.exists(dest):
                shutil.rmtree(dest)
            shutil.copytree(os.path.join(SKILLS, name), dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            print(f"installed {name} -> {dest}")
        return 0
    os.makedirs(args.dist, exist_ok=True)
    for name in names:
        path = os.path.join(args.dist, f"{name}.zip")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for full, arc in iter_files(name):
                zf.write(full, arc)
        print(f"created {os.path.relpath(path, ROOT)} ({os.path.getsize(path) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
