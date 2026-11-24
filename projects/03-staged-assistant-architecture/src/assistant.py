"""Staged assistant: answers at the CHEAPEST stage that works.

  0    direct pandas lookup (metric + company + month), no LLM
  0.5  period parser; a month outside the series is answered right away, no LLM
  1    lean context + LLM, for interpretation questions ("explique", "resuma")
  2    LLM writes analysis code, validated and run in a sandbox, for rankings and averages
  3    controlled fallback

Golden rules (each one avoids an LLM call or an invented answer):
  * An indicator without a source, a month outside the series and a suppressed value NEVER escalate.
  * The LLM only sees filtered, size-limited context, never the whole Gold.
  * The LLM is a pluggable function: `llm(prompt) -> str`. No credential lives in this code.

Language: the questions, keywords and answer strings are in Portuguese. The routing is
language-independent; supporting another language means adding keyword lists and answer strings.
"""
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from periods import label, norm, parse_period
from sandbox import SandboxError, run_sandboxed

Tables = dict[str, pd.DataFrame]
LLM = Callable[[str], str]
CodeGen = Callable[[str, dict[str, list[str]]], str]

GOLD_DIR = Path(__file__).resolve().parents[2] / "02-etl-consolidation-pattern" / "out" / "gold"
FILES = {"headcount": "Headcount - Gender (Core).xlsx", "turnover": "Turnover - Monthly.xlsx",
         "tth": "Time to Hire - Monthly.xlsx", "regret": "Regrettable Turnover.xlsx",
         "kpi": "KPI Card - Monthly.xlsx"}
CONTEXT_BUDGET = 1500  # characters sent to the LLM

# Order matters: most specific first ("regrettable turnover" contains "turnover").
METRICS: dict[str, dict[str, Any]] = {
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
    """One answer: the stage that produced it, its kind, the text and, for stage 2, the code that ran."""

    stage: float
    kind: str
    text: str
    code: str = ""


def load_tables(gold_dir: Path | str = GOLD_DIR) -> Tables:
    """Reads the Gold spreadsheets and normalizes the month column to 'YYYY-MM-DD' text."""
    tables: Tables = {}
    for key, name in FILES.items():
        path = Path(gold_dir) / name
        if not path.exists():
            raise FileNotFoundError(f"{path} does not exist. Run project 02 (consolidate.py and build_gold.py) first.")
        tables[key] = pd.read_excel(path)
    tables["tth"] = tables["tth"].rename(columns={"closed_month": "month"})
    for key in ("headcount", "turnover", "tth"):
        tables[key]["month"] = tables[key]["month"].astype(str).str[:10]
    return tables


def detect_metric(q: str) -> str | None:
    """Returns the key of the first metric whose keywords appear in the question, or None."""
    nq = norm(q)
    for key, spec in METRICS.items():
        if any(w in nq for w in spec["words"]):
            return key
    return None


def detect_companies(q: str, companies: list[str]) -> list[str]:
    """Returns the companies named in the question, by full name or by their last word."""
    nq = norm(q)
    found = []
    for c in companies:
        short = norm(c).split()[-1]
        if norm(c) in nq or re.search(rf"\b{re.escape(short)}\b", nq):
            found.append(c)
    return found


def classify(q: str, metric: str | None) -> str:
    """Classifies the question as 'explain', 'analysis', 'lookup' or 'other'."""
    nq = norm(q)
    if RE_EXPLAIN.search(nq):
        return "explain"
    if RE_ANALYSIS.search(nq):
        return "analysis"
    return "lookup" if metric else "other"


def _fmt(kind: str, v: float) -> str:
    """Formats a value as an integer, a percentage or a number of days (Brazilian decimal comma)."""
    if kind == "int":
        return f"{int(v)}"
    if kind == "pct":
        return f"{v * 100:.1f}%".replace(".", ",")
    return f"{v:.1f} dias".replace(".", ",")


def _value_line(row: pd.Series | None, spec: dict[str, Any]) -> str:
    """Text for one company: the value, 'suppressed due to group size' or 'no data'."""
    if row is None:
        return "sem dado no período"
    if bool(row.get("suppressed", False)):
        return "não divulgado por tamanho de grupo"
    v = row[spec["value"]]
    return "sem dado no período" if pd.isna(v) else _fmt(spec["fmt"], v)


def stage0(q: str, metric: str, iso: str | None, t: Tables) -> Answer:
    """Stage 0: direct lookup of one metric for the requested companies and month."""
    spec = METRICS[metric]
    df = t[spec["table"]]
    all_companies = sorted(t["headcount"]["company"].unique())
    companies = detect_companies(q, all_companies) or all_companies
    if spec["monthly"]:
        month = iso or sorted(t["headcount"]["month"].unique())[-1]  # last month of the whole series
        title, sub = f"{spec['title']} em {label(month)}", df[df["month"] == month]
    else:
        title, sub = f"{spec['title']} (todo o período)", df
    lines = []
    for c in companies:
        row = sub[sub["company"] == c]
        lines.append(f"- {c}: {_value_line(row.iloc[0] if len(row) else None, spec)}")
    return Answer(0, "lookup", title + ":\n" + "\n".join(lines))


def build_context(metric: str | None, companies: list[str], t: Tables, budget: int = CONTEXT_BUDGET) -> str:
    """Builds the filtered, size-limited context sent to the LLM: last 6 months of the relevant table."""
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


def stage1(q: str, metric: str | None, t: Tables, llm: LLM) -> Answer:
    """Stage 1: asks the LLM, giving it only the filtered context."""
    companies = detect_companies(q, sorted(t["headcount"]["company"].unique()))
    prompt = PROMPT.format(context=build_context(metric, companies, t), question=q)
    return Answer(1, "llm", llm(prompt))


def stage2(q: str, t: Tables, codegen: CodeGen) -> Answer | None:
    """Stage 2: runs generated analysis code in the sandbox. Returns None if it is rejected or fails."""
    try:
        code = codegen(q, {k: list(df.columns) for k, df in t.items()})
        result = run_sandboxed(code, {k: df.copy() for k, df in t.items()})
    except (SandboxError, NotImplementedError):
        return None
    text = result.to_string() if hasattr(result, "to_string") else str(result)
    return Answer(2, "code", "Resultado da análise:\n" + text, code=code)


def answer(q: str, t: Tables, llm: LLM | None = None, codegen: CodeGen | None = None) -> Answer:
    """Routes the question to the cheapest stage that can answer it."""
    metric = detect_metric(q)
    if metric and METRICS[metric].get("unavailable"):  # never escalates: an LLM would make it up
        return Answer(0, "unavailable", f"{METRICS[metric]['title']}: não disponível nas fontes atuais. "
                                         "Não vou estimar.")
    months = sorted(t["headcount"]["month"].unique())
    iso, status = parse_period(q, months)
    if status == "out_of_range":  # stage 0.5: stops it before any model call
        return Answer(0.5, "out_of_range",
                      f"Período fora da série disponível ({label(months[0])} a {label(months[-1])}).")
    kind = classify(q, metric)
    if kind == "lookup" and metric:
        return stage0(q, metric, iso, t)
    if kind == "analysis" and codegen:
        a = stage2(q, t, codegen)
        if a:
            return a
    if kind in ("analysis", "explain") and llm:
        return stage1(q, metric, t, llm)
    return Answer(3, "fallback", FALLBACK)
