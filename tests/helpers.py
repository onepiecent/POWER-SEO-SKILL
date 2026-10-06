"""Tiện ích dùng chung cho test: đường dẫn script, chạy main() và bắt đầu ra."""
import contextlib
import csv
import io
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXAMPLES = os.path.join(ROOT, "examples")
for sub in ("keyword-clustering", "topic-map", "internal-link-planner", "editorial-calendar", "content-brief",
            "helpful-content-editor", "product-slot", "claims-compliance-check"):
    path = os.path.join(ROOT, "skills", sub, "scripts")
    if path not in sys.path:
        sys.path.insert(0, path)


def run_main(main, argv):
    """Chạy main(argv), trả (mã thoát, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as exc:  # argparse / raise SystemExit("msg")
            code = exc.code if isinstance(exc.code, int) else 1
            if isinstance(exc.code, str):
                err.write(exc.code)
    return code, out.getvalue(), err.getvalue()


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_text(path, text, encoding="utf-8"):
    with open(path, "w", encoding=encoding, newline="") as fh:
        fh.write(text)


def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()
