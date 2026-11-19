"""Publication guard: blocks leaks of data or internal context.

Usage:
    py tools/guard.py            # scans the whole folder
    py tools/guard.py --staged   # scans only what is staged in git (pre-commit hook)

What it looks for:
  1. forbidden terms listed in tools/guard_terms.local.txt (local file, kept out of git)
  2. CPF numbers with a VALID check digit (synthetic CPFs are invalid on purpose)
  3. e-mail addresses, except example.*, noreply and those allowed with "allow:" in the local file
  4. machine and corporate-cloud paths, GUIDs and base64-embedded images
  5. data/binary extensions and large files
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TERMS_FILE = ROOT / "tools" / "guard_terms.local.txt"

SKIP_DIRS = {".git", "out", "__pycache__", ".venv", "node_modules"}
BLOCKED_EXT = {".parquet", ".xlsx", ".xlsb", ".xlsm", ".pbix", ".pptx", ".pem", ".key", ".db", ".sqlite"}
TEXT_EXT = {".md", ".txt", ".py", ".csv", ".html", ".json", ".yml", ".yaml", ".js", ".css", ".sql", ".ps1", ".toml", ""}
MAX_BYTES = 1_500_000

RE_CPF = re.compile(r"(?<!\d)(\d{3}\.?\d{3}\.?\d{3}-?\d{2})(?!\d)")
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
RE_GUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
RE_B64 = re.compile(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=]{2000,}")
RE_PATH = re.compile(r"[A-Za-z]:\\Users\\|One" r"Drive|share" r"point\.com|\\\\[\w.-]+\\", re.I)


def cpf_is_valid(digits: str) -> bool:
    d = [int(c) for c in digits]
    if len(set(d)) == 1:
        return False
    for n in (9, 10):
        s = sum(v * w for v, w in zip(d[:n], range(n + 1, 1, -1)))
        r = (s * 10) % 11
        if (0 if r == 10 else r) != d[n]:
            return False
    return True


def load_terms():
    terms, allow = [], set()
    if not TERMS_FILE.exists():
        print("WARNING: tools/guard_terms.local.txt does not exist; only the generic checks run.")
        return terms, allow
    for line in TERMS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("allow:"):
            allow.add(line[6:].strip().lower())
        else:
            terms.append(line.lower())
    return terms, allow


def candidate_files(staged: bool):
    if staged:
        out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return [ROOT / p for p in out.splitlines() if p]
    return [p for p in ROOT.rglob("*")
            if p.is_file() and not (set(p.relative_to(ROOT).parts) & SKIP_DIRS)]


def scan(path: Path, terms, allow):
    rel = path.relative_to(ROOT).as_posix()
    if rel == "tools/guard_terms.local.txt":
        return []
    problems = []
    if path.suffix.lower() in BLOCKED_EXT:
        problems.append((rel, 0, f"blocked extension ({path.suffix})"))
    try:
        size = path.stat().st_size
    except OSError:
        return problems
    if size > MAX_BYTES:
        problems.append((rel, 0, f"large file ({size // 1024} KB)"))
    if path.suffix.lower() not in TEXT_EXT:
        return problems
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        problems.append((rel, 0, "not UTF-8; review manually"))
        return problems

    low_name = rel.lower()
    for t in terms:
        if t in low_name:
            problems.append((rel, 0, f"forbidden term in file name: '{t}'"))
    for i, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        for t in terms:
            if t in low:
                problems.append((rel, i, f"forbidden term: '{t}'"))
        for m in RE_CPF.finditer(line):
            digits = re.sub(r"\D", "", m.group(1))
            if cpf_is_valid(digits):
                problems.append((rel, i, "possible valid CPF"))
        for m in RE_EMAIL.finditer(line):
            e = m.group(0).lower()
            if e in allow or "example." in e or "noreply" in e:
                continue
            problems.append((rel, i, "e-mail address found"))
        if RE_GUID.search(line):
            problems.append((rel, i, "GUID (possible internal ID)"))
        if RE_PATH.search(line) and rel != "tools/guard.py":
            problems.append((rel, i, "machine/cloud path"))
        if RE_B64.search(line):
            problems.append((rel, i, "base64-embedded image (logo/brand?)"))
    return problems


def main():
    staged = "--staged" in sys.argv
    terms, allow = load_terms()
    files = candidate_files(staged)
    found = []
    for f in files:
        found.extend(scan(f, terms, allow))
    if found:
        print(f"BLOCKED: {len(found)} finding(s) in {len(files)} file(s)\n")
        for rel, line, why in found:
            print(f"  {rel}{':' + str(line) if line else ''}  {why}")
        sys.exit(1)
    print(f"OK: {len(files)} file(s) checked, no findings.")


if __name__ == "__main__":
    main()
