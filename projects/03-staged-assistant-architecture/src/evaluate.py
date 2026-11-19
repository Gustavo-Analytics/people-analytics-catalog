"""Measures which stage resolves each question and how many LLM calls were spent.

Usage: py src/evaluate.py [-v]
Exits with code 1 if any expected stage or text does not match.
"""
import csv
import sys
from collections import Counter
from pathlib import Path

from assistant import answer, load_tables
from stubs import StubCodegen, StubLLM

QUESTIONS = Path(__file__).resolve().parents[1] / "eval_questions.csv"


def main(verbose: bool = False) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    tables = load_tables()
    llm, codegen = StubLLM(), StubCodegen()
    rows = list(csv.DictReader(open(QUESTIONS, encoding="utf-8")))
    stages, failures = Counter(), []

    for r in rows:
        a = answer(r["question"], tables, llm=llm, codegen=codegen)
        stages[a.stage] += 1
        ok = float(a.stage) == float(r["expected_stage"]) and r["must_contain"] in a.text
        print(f"[{'ok' if ok else 'FAILED'}] stage {a.stage:<3} {a.kind:<12} {r['question']}")
        if verbose or not ok:
            print("      " + a.text.replace("\n", "\n      "))
            if a.code:
                print("      code: " + a.code.replace("\n", " ; "))
        if not ok:
            failures.append(r["question"])

    total = len(rows)
    print(f"\n{total} questions | LLM calls: {llm.calls} | code generation: {codegen.calls}")
    for stage in sorted(stages):
        print(f"  stage {stage}: {stages[stage]} ({stages[stage] / total:.0%})")
    print(f"  without LLM: {sum(stages[s] for s in stages if s in (0, 0.5, 3))} of {total}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main("-v" in sys.argv))
