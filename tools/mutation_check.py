"""Checks that the tests catch bugs: injects deliberate defects into a COPY of the repository.

Usage: py tools/mutation_check.py

Each defect (a "mutant") is applied alone to the copy and the whole test suite runs against it.
The suite must FAIL for every mutant; a surviving mutant means a check is missing from the tests.
The working tree is never touched. Takes a few minutes.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
IGNORE = shutil.ignore_patterns(".git", ".venv", "out", "__pycache__", ".mypy_cache", ".ruff_cache",
                                ".hypothesis", "*.pyc")

ETL = "projects/02-etl-consolidation-pattern/src"
ASSISTANT = "projects/03-staged-assistant-architecture/src"


class Mutant(NamedTuple):
    """One deliberate defect: replace `old` by `new` in `file`."""

    file: str
    old: str
    new: str
    why: str


MUTANTS = [
    Mutant(f"{ETL}/consolidate.py", ".str.zfill(11)", ".str.zfill(10)",
           "person key restored to 10 digits instead of 11"),
    Mutant(f"{ETL}/consolidate.py",
           'df.drop_duplicates(subset=["month", "employee_id"], keep="last")',
           'df.drop_duplicates(subset=["month", "employee_id"], keep="first")',
           "deduplication keeps the old version of a month"),
    Mutant(f"{ETL}/consolidate.py",
           'df = read_many(SAMPLE / "exits")\n    df["person_key"] = norm_key(df["person_key"])',
           'df = read_many(SAMPLE / "exits")',
           "terminations are not key-normalized before deduplication"),
    Mutant(f"{ETL}/build_gold.py", "mask = out[count_col] < k", "mask = out[count_col] <= k",
           "k-anonymity suppresses groups of exactly k"),
    Mutant(f"{ETL}/build_gold.py", 'core = hc[hc["contract_type"].isin(["CLT", "PJ"])]', "core = hc",
           "the standardized gender view includes interns and apprentices"),
    Mutant(f"{ETL}/build_gold.py",
           't["turnover_pct"] = (t["exits_total"] / t["headcount"]).round(4)',
           't["turnover_pct"] = (t["exits_total"] / t["headcount"] * 100).round(4)',
           "turnover published on the wrong scale (x100)"),
    Mutant(f"{ETL}/build_gold.py",
           'assert not gold_cols & {"person_key", "employee_id", "source_file"}, "a person column leaked into Gold"',
           "assert True",
           "the check for person columns in Gold is removed"),
    Mutant(f"{ASSISTANT}/assistant.py", 'if metric and METRICS[metric].get("unavailable"):', "if False:",
           "an indicator without a source is escalated to the LLM"),
    Mutant(f"{ASSISTANT}/assistant.py", 'if status == "out_of_range":', "if False:",
           "a month outside the series is escalated to the LLM"),
    Mutant(f"{ASSISTANT}/sandbox.py", 'if a.startswith("_") or a in BLOCKED_ATTRS', "if a in BLOCKED_ATTRS",
           "the sandbox allows private attributes"),
    Mutant("synthetic-data/generate.py", "d2 = (dv(d + [d1]) + 1) % 10  # forces it to be invalid",
           "d2 = dv(d + [d1]) % 10", "synthetic CPFs become valid"),
    Mutant("tools/guard.py", "if len(set(d)) == 1:", "if False:",
           "a CPF with repeated digits is accepted as valid"),
]


def main() -> int:
    """Runs the suite against every mutant; returns 0 if all were caught, 1 otherwise."""
    survivors: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "repo"
        shutil.copytree(ROOT, work, ignore=IGNORE)
        for number, mutant in enumerate(MUTANTS, 1):
            path = work / mutant.file
            original = path.read_text(encoding="utf-8")
            if mutant.old not in original:
                print(f"[{number:2}/{len(MUTANTS)}] NOT APPLIED  {mutant.why}")
                survivors.append(f"{mutant.why} (the code to change was not found)")
                continue
            path.write_text(original.replace(mutant.old, mutant.new), encoding="utf-8")
            try:
                code = subprocess.run([sys.executable, "tools/run_tests.py"], cwd=work, capture_output=True).returncode
            finally:
                path.write_text(original, encoding="utf-8")
            caught = code != 0
            print(f"[{number:2}/{len(MUTANTS)}] {'caught  ' if caught else 'SURVIVED'}  {mutant.why}")
            if not caught:
                survivors.append(mutant.why)
    print(f"\n{len(MUTANTS) - len(survivors)} of {len(MUTANTS)} defects caught by the tests")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
