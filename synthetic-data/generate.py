"""Gera um conjunto de dados de RH 100% sintético (sem pessoas nem empresa reais).

Reproduz de propósito os problemas que um ETL real encontra:
  * arquivos mensais separados que precisam ser consolidados
  * desligamentos repetidos em relatórios cumulativos (duplicatas)
  * CPF com zero à esquerda, às vezes gravado como número (zero perdido)
  * lista de talentos que só traz o ID do funcionário, sem CPF (ponte ID -> CPF)

Uso: py synthetic-data/generate.py
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 42
OUT = Path(__file__).resolve().parent / "sample"
N_MONTHS = 12
FIRST_MONTH = (2025, 11)

COMPANIES = [("Acme Retail", 0.50), ("Acme Logistics", 0.18), ("Acme Pay", 0.12),
             ("Acme Mobile", 0.12), ("Acme Tech", 0.08)]
DEPARTMENTS = ["Operations", "Commercial", "Technology", "Finance", "People", "Marketing"]
CONTRACTS = [("CLT", 0.70), ("PJ", 0.12), ("Intern", 0.10), ("Apprentice", 0.08)]
GENDERS = [("F", 0.46), ("M", 0.52), ("Other", 0.02)]
SENIORITY = ["Junior", "Mid", "Senior", "Lead", "Manager"]
REASONS = ["Better offer", "Career change", "Relocation", "Restructuring", "Performance"]


def pick(rng, pairs):
    r, acc = rng.random(), 0.0
    for value, w in pairs:
        acc += w
        if r <= acc:
            return value
    return pairs[-1][0]


def fake_cpf(rng, used):
    """CPF sintético com dígito verificador ERRADO de propósito (nunca é um CPF real)."""
    def dv(nums):
        s = sum(n * w for n, w in zip(nums, range(len(nums) + 1, 1, -1)))
        r = (s * 10) % 11
        return 0 if r == 10 else r

    while True:
        d = [rng.randint(0, 9) for _ in range(9)]
        if rng.random() < 0.30:
            d[0] = 0  # garante casos com zero à esquerda
        d1 = dv(d)
        d2 = (dv(d + [d1]) + 1) % 10  # força inválido
        cpf = "".join(map(str, d + [d1, d2]))
        if cpf not in used:
            used.add(cpf)
            return cpf


def month_start(i):
    y, m = FIRST_MONTH
    total = (m - 1) + i
    return date(y + total // 12, total % 12 + 1, 1)


def main():
    rng = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "headcount").mkdir(exist_ok=True)
    (OUT / "exits").mkdir(exist_ok=True)

    used, people = set(), []
    for n in range(520):
        hire = rng.randint(-30, N_MONTHS - 1)
        term = None
        if rng.random() < 0.22:
            lo = max(hire + 1, 0)
            if lo <= N_MONTHS - 1:
                term = rng.randint(lo, N_MONTHS - 1)
        people.append({
            "employee_id": 10000 + n,
            "person_key": fake_cpf(rng, used),
            "company": pick(rng, COMPANIES),
            "department": rng.choice(DEPARTMENTS),
            "contract_type": pick(rng, CONTRACTS),
            "gender": pick(rng, GENDERS),
            "seniority": rng.choice(SENIORITY),
            "hire": hire,
            "term": term,
            "talent": rng.random() < 0.08,
            "initiative": "Employee" if rng.random() < 0.65 else "Company",
            "reason": rng.choice(REASONS),
        })

    hc_cols = ["month", "employee_id", "person_key", "company", "department",
               "contract_type", "gender", "seniority"]
    for i in range(N_MONTHS):
        mdate = month_start(i)
        rows = [[mdate.isoformat(), p["employee_id"], p["person_key"], p["company"], p["department"],
                 p["contract_type"], p["gender"], p["seniority"]]
                for p in people if p["hire"] <= i and (p["term"] is None or p["term"] > i)]
        with open(OUT / "headcount" / f"headcount_{mdate:%Y-%m}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(hc_cols)
            w.writerows(rows)

    ex_cols = ["person_key", "employee_id", "company", "exit_date", "initiative", "reason"]
    prev_rows = []
    for i in range(N_MONTHS):
        mdate = month_start(i)
        rows = []
        for p in people:
            if p["term"] == i:
                exit_day = mdate + timedelta(days=rng.randint(0, 27))
                key = p["person_key"]
                if rng.random() < 0.03:
                    key = str(int(key))  # zero à esquerda perdido (gravado como número)
                rows.append([key, p["employee_id"], p["company"], exit_day.isoformat(),
                             p["initiative"], p["reason"]])
        # relatório cumulativo: repete parte dos desligamentos do mês anterior
        dupes = [r for r in prev_rows if rng.random() < 0.20]
        with open(OUT / "exits" / f"exits_{mdate:%Y-%m}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(ex_cols)
            w.writerows(rows + dupes)
        prev_rows = rows

    with open(OUT / "talent_calibration.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["employee_id", "cycle"])
        for p in people:
            if p["talent"]:
                w.writerow([p["employee_id"], "Cycle-1"])

    req_cols = ["req_id", "company", "department", "opened_date", "closed_date", "source"]
    with open(OUT / "requisitions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(req_cols)
        for r in range(160):
            opened = month_start(rng.randint(0, N_MONTHS - 1)) + timedelta(days=rng.randint(0, 27))
            closed = opened + timedelta(days=rng.randint(12, 75)) if rng.random() < 0.85 else None
            w.writerow([f"R{1000 + r}", pick(rng, COMPANIES), rng.choice(DEPARTMENTS),
                        opened.isoformat(), closed.isoformat() if closed else "",
                        "Internal" if rng.random() < 0.22 else "External"])

    print(f"Dados sintéticos gerados em {OUT}")


if __name__ == "__main__":
    main()
