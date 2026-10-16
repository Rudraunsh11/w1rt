"""Repo-wide safety guard: fails if any .py file can execute input or call off-host."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "venv", "env", "__pycache__"}

FORBIDDEN = {
    "subprocess": re.compile(r"\bsubprocess\b"),
    "os.system": re.compile(r"\bos\.system\s*\("),
    "os.popen": re.compile(r"\bos\.popen\s*\("),
    "eval(": re.compile(r"\beval\s*\("),
    "exec(": re.compile(r"\bexec\s*\("),
    "bind 0.0.0.0": re.compile(r"0\.0\.0\.0"),
    "non-loopback URL": re.compile(r"https?://(?!127\.0\.0\.1[:/])"),
}


def _py_files():
    for path in ROOT.rglob("*.py"):
        if SKIP_DIRS & set(path.relative_to(ROOT).parts):
            continue
        if path.resolve() == pathlib.Path(__file__).resolve():
            continue
        yield path


def test_no_forbidden_patterns():
    hits = []
    for path in _py_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, rx in FORBIDDEN.items():
                if rx.search(line):
                    hits.append(f"{path.relative_to(ROOT)}:{lineno}: {name}")
    assert not hits, "Safety rule broken:\n" + "\n".join(hits)
