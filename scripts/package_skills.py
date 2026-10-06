#!/usr/bin/env python3
"""Đóng gói từng skill thành zip (để tải lên claude.ai) hoặc cài vào thư mục skill của Claude Code.

    python3 scripts/package_skills.py                      # tạo dist/<skill>.zip
    python3 scripts/package_skills.py --install ~/.claude/skills   # sao chép các skill vào thư mục đích
    python3 scripts/package_skills.py --skills keyword-clustering topic-map

Mỗi skill tự đóng gói: zip chứa thư mục <skill>/ với SKILL.md ở gốc. Bỏ qua __pycache__ và *.pyc.
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
        raise SystemExit("Không có skill: " + ", ".join(missing))
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
    ap.add_argument("--skills", nargs="*", help="chỉ đóng gói các skill này")
    ap.add_argument("--install", metavar="DIR", help="sao chép skill vào DIR thay vì tạo zip")
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
            print(f"đã cài {name} -> {dest}")
        return 0
    os.makedirs(args.dist, exist_ok=True)
    for name in names:
        path = os.path.join(args.dist, f"{name}.zip")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for full, arc in iter_files(name):
                zf.write(full, arc)
        print(f"đã tạo {os.path.relpath(path, ROOT)} ({os.path.getsize(path) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
