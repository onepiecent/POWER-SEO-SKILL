"""Repo health checks: valid frontmatter, referenced files exist, scripts run with --help."""
import glob
import os
import re
import subprocess
import sys
import unittest

import helpers
from helpers import ROOT

SKILLS = sorted(glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md")))
REF_RX = re.compile(r"`((?:references|assets|scripts|examples|docs|skills|tests)/[^`\s<>*|]+\.(?:md|json|py|txt|csv))`")


def frontmatter(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return (m.group(1) if m else None), text


class SkillFiles(unittest.TestCase):
    def test_nine_skills_present(self):
        self.assertEqual(len(SKILLS), 9)

    def test_frontmatter_is_valid_yaml(self):
        try:
            import yaml
        except ImportError:
            yaml = None
        for path in SKILLS:
            with self.subTest(skill=path):
                fm, _ = frontmatter(path)
                self.assertIsNotNone(fm, "missing frontmatter")
                name = re.search(r"^name:\s*(.+)$", fm, re.M).group(1).strip()
                desc = re.search(r"^description:\s*(.+)$", fm, re.M).group(1)
                self.assertEqual(name, os.path.basename(os.path.dirname(path)))
                self.assertRegex(name, r"^[a-z0-9-]{1,64}$")
                self.assertLessEqual(len(desc), 1024)
                self.assertNotIn(": ", desc, "a ': ' breaks an unquoted YAML scalar")
                if yaml:
                    data = yaml.safe_load(fm)
                    self.assertEqual(set(data), {"name", "description"})

    def test_referenced_files_exist(self):
        for path in SKILLS:
            skill_dir = os.path.dirname(path)
            _, text = frontmatter(path)
            for ref in set(REF_RX.findall(text)):
                with self.subTest(skill=os.path.basename(skill_dir), ref=ref):
                    candidates = [os.path.join(skill_dir, ref), os.path.join(ROOT, ref)]
                    # cross-references to references/... of another skill are written with the skill name
                    candidates += glob.glob(os.path.join(ROOT, "skills", "*", ref))
                    self.assertTrue(any(os.path.exists(c) for c in candidates), ref)

    def test_every_script_has_help(self):
        for script in glob.glob(os.path.join(ROOT, "skills", "*", "scripts", "*.py")):
            if os.path.basename(script) in ("kw_text.py", "kw_ingest.py", "plan_qa.py", "published.py", "table_io.py"):  # modules
                continue
            with self.subTest(script=os.path.basename(script)):
                r = subprocess.run([sys.executable, script, "--help"], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("usage", r.stdout.lower())

    def test_json_assets_load(self):
        import json
        for p in glob.glob(os.path.join(ROOT, "skills", "*", "assets", "*.json")) + glob.glob(os.path.join(ROOT, "examples", "*.json")):
            with self.subTest(file=os.path.basename(p)):
                with open(p, encoding="utf-8") as fh:
                    json.load(fh)

    def test_taxonomy_regexes_compile_and_have_labels(self):
        import kw_text
        tax = kw_text.Taxonomy.load()
        for facet in ("occasion", "interest", "recipient"):
            for key, spec in tax.data["facets"][facet]["values"].items():
                self.assertIn("label", spec, f"{facet}.{key}")


if __name__ == "__main__":
    unittest.main()
