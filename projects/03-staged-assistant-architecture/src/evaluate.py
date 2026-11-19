"""Mede em que estágio cada pergunta é resolvida e quantas chamadas de LLM foram gastas.

Uso: py src/evaluate.py [-v]
Sai com código 1 se algum estágio ou texto esperado não bater.
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
        print(f"[{'ok' if ok else 'FALHOU'}] estágio {a.stage:<3} {a.kind:<12} {r['question']}")
        if verbose or not ok:
            print("      " + a.text.replace("\n", "\n      "))
            if a.code:
                print("      código: " + a.code.replace("\n", " ; "))
        if not ok:
            failures.append(r["question"])

    total = len(rows)
    print(f"\n{total} perguntas | chamadas de LLM: {llm.calls} | geração de código: {codegen.calls}")
    for stage in sorted(stages):
        print(f"  estágio {stage}: {stages[stage]} ({stages[stage] / total:.0%})")
    print(f"  sem LLM: {sum(stages[s] for s in stages if s in (0, 0.5, 3))} de {total}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main("-v" in sys.argv))
