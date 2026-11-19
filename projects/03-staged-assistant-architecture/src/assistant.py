"""Assistente em estágios: responde no estágio MAIS BARATO que resolva.

  0    lookup direto em pandas (métrica + empresa + mês), sem LLM
  0.5  parser de período; mês fora da série é respondido na hora, sem LLM
  1    contexto enxuto + LLM, para perguntas de interpretação ("explique", "resuma")
  2    LLM gera código de análise, validado e executado em sandbox, para ranking e médias
  3    fallback controlado

Regras de ouro (cada uma evita uma chamada de LLM ou uma resposta inventada):
  * Indicador sem fonte, mês fora da série e valor suprimido NUNCA sobem de estágio.
  * O LLM só vê contexto filtrado e limitado em tamanho, nunca o Gold inteiro.
  * O LLM é uma função plugável: `llm(prompt) -> str`. Nenhuma credencial vive neste código.
"""
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from periods import label, norm, parse_period
from sandbox import SandboxError, run_sandboxed

GOLD_DIR = Path(__file__).resolve().parents[2] / "02-etl-consolidation-pattern" / "out" / "gold"
FILES = {"headcount": "Headcount - Gender (Core).xlsx", "turnover": "Turnover - Monthly.xlsx",
         "tth": "Time to Hire - Monthly.xlsx", "regret": "Regrettable Turnover.xlsx",
         "kpi": "KPI Card - Monthly.xlsx"}
CONTEXT_BUDGET = 1500  # caracteres enviados ao LLM

# Ordem importa: o mais específico primeiro ("regrettable turnover" contém "turnover").
METRICS = {
    "regret": {"title": "Regrettable turnover", "table": "regret", "value": "regrettable_pct",
               "fmt": "pct", "monthly": False,
               "words": ["regrettable", "talentos que sairam", "perda de talentos", "saida de talentos"]},
    "tth": {"title": "Time to hire", "table": "tth", "value": "avg_days", "fmt": "days", "monthly": True,
            "words": ["time to hire", "tempo de contratacao", "tempo para contratar", "tth"]},
    "engagement": {"title": "Engajamento", "unavailable": True,
                   "words": ["engajamento", "clima", "satisfacao", "engagement"]},
    "women": {"title": "Percentual de mulheres (vínculos principais)", "table": "headcount",
              "value": "women_pct", "fmt": "pct", "monthly": True,
              "words": ["mulher", "genero", "diversidade"]},
    "turnover": {"title": "Turnover", "table": "turnover", "value": "turnover_pct", "fmt": "pct",
                 "monthly": True, "words": ["turnover", "rotatividade", "desligamento"]},
    "headcount": {"title": "Headcount (vínculos principais)", "table": "headcount", "value": "headcount",
                  "fmt": "int", "monthly": True,
                  "words": ["headcount", "quantas pessoas", "quantos colaboradores", "quantos funcionarios",
                            "tamanho do time"]},
}
RE_ANALYSIS = re.compile(r"\b(ranking|maior|menor|media|top)\b")
RE_EXPLAIN = re.compile(r"\b(explique|explica|resuma|resumo|por que|porque|interprete)\b")

PROMPT = """Você é um assistente de People Analytics. Use SOMENTE o contexto abaixo.
Se faltar dado, responda "não disponível nas fontes atuais". Nunca estime e nunca reconstrua valores suprimidos.
CONTEXTO:
{context}
PERGUNTA:
{question}"""
FALLBACK = ("Não encontrei isso nas fontes atuais. Posso responder: headcount, percentual de mulheres, "
            "turnover, time to hire e regrettable turnover, por empresa e mês.")


@dataclass
class Answer:
    stage: float
    kind: str
    text: str
    code: str = ""


def load_tables(gold_dir=GOLD_DIR) -> dict:
    tables = {}
    for key, name in FILES.items():
        path = Path(gold_dir) / name
        if not path.exists():
            raise FileNotFoundError(f"{path} não existe. Rode o projeto 02 (consolidate.py e build_gold.py) antes.")
        tables[key] = pd.read_excel(path)
    tables["tth"] = tables["tth"].rename(columns={"closed_month": "month"})
    for key in ("headcount", "turnover", "tth"):
        tables[key]["month"] = tables[key]["month"].astype(str).str[:10]
    return tables


def detect_metric(q: str):
    nq = norm(q)
    for key, spec in METRICS.items():
        if any(w in nq for w in spec["words"]):
            return key
    return None


def detect_companies(q: str, companies: list) -> list:
    nq = norm(q)
    found = []
    for c in companies:
        short = norm(c).split()[-1]
        if norm(c) in nq or re.search(rf"\b{re.escape(short)}\b", nq):
            found.append(c)
    return found


def classify(q: str, metric) -> str:
    nq = norm(q)
    if RE_EXPLAIN.search(nq):
        return "explain"
    if RE_ANALYSIS.search(nq):
        return "analysis"
    return "lookup" if metric else "other"


def _fmt(kind: str, v) -> str:
    if kind == "int":
        return f"{int(v)}"
    if kind == "pct":
        return f"{v * 100:.1f}%".replace(".", ",")
    return f"{v:.1f} dias".replace(".", ",")


def _value_line(row, spec) -> str:
    if row is None:
        return "sem dado no período"
    if bool(row.get("suppressed", False)):
        return "não divulgado por tamanho de grupo"
    v = row[spec["value"]]
    return "sem dado no período" if pd.isna(v) else _fmt(spec["fmt"], v)


def stage0(q: str, metric: str, iso, t: dict) -> Answer:
    spec = METRICS[metric]
    df = t[spec["table"]]
    all_companies = sorted(t["headcount"]["company"].unique())
    companies = detect_companies(q, all_companies) or all_companies
    if spec["monthly"]:
        month = iso or sorted(t["headcount"]["month"].unique())[-1]  # último mês da série inteira
        title, sub = f"{spec['title']} em {label(month)}", df[df["month"] == month]
    else:
        title, sub = f"{spec['title']} (todo o período)", df
    lines = []
    for c in companies:
        row = sub[sub["company"] == c]
        lines.append(f"- {c}: {_value_line(row.iloc[0] if len(row) else None, spec)}")
    return Answer(0, "lookup", title + ":\n" + "\n".join(lines))


def build_context(metric, companies: list, t: dict, budget: int = CONTEXT_BUDGET) -> str:
    keys = [METRICS[metric]["table"]] if metric and "table" in METRICS[metric] else ["headcount", "turnover"]
    parts = []
    for key in keys:
        df = t[key]
        if companies:
            df = df[df["company"].isin(companies)]
        if "month" in df:
            df = df[df["month"].isin(sorted(df["month"].unique())[-6:])]
        parts.append(f"# {key}\n" + df.to_csv(index=False))
    return "\n".join(parts)[:budget]


def stage1(q: str, metric, t: dict, llm) -> Answer:
    companies = detect_companies(q, sorted(t["headcount"]["company"].unique()))
    prompt = PROMPT.format(context=build_context(metric, companies, t), question=q)
    return Answer(1, "llm", llm(prompt))


def stage2(q: str, t: dict, codegen):
    try:
        code = codegen(q, {k: list(df.columns) for k, df in t.items()})
        result = run_sandboxed(code, {k: df.copy() for k, df in t.items()})
    except (SandboxError, NotImplementedError):
        return None
    text = result.to_string() if hasattr(result, "to_string") else str(result)
    return Answer(2, "code", "Resultado da análise:\n" + text, code=code)


def answer(q: str, t: dict, llm=None, codegen=None) -> Answer:
    metric = detect_metric(q)
    if metric and METRICS[metric].get("unavailable"):  # nunca sobe de estágio: o LLM inventaria
        return Answer(0, "unavailable", f"{METRICS[metric]['title']}: não disponível nas fontes atuais. "
                                         "Não vou estimar.")
    months = sorted(t["headcount"]["month"].unique())
    iso, status = parse_period(q, months)
    if status == "out_of_range":  # estágio 0.5: barra antes de qualquer chamada de modelo
        return Answer(0.5, "out_of_range",
                      f"Período fora da série disponível ({label(months[0])} a {label(months[-1])}).")
    kind = classify(q, metric)
    if kind == "lookup":
        return stage0(q, metric, iso, t)
    if kind == "analysis" and codegen:
        a = stage2(q, t, codegen)
        if a:
            return a
    if kind in ("analysis", "explain") and llm:
        return stage1(q, metric, t, llm)
    return Answer(3, "fallback", FALLBACK)
