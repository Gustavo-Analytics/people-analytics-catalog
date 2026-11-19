"""Camada Gold: agrega, aplica k-anonimato e grava planilhas prontas para consumo.

Entrada : out/bronze/*.parquet
Saída   : out/gold/*.xlsx  (sem coluna de pessoa; é a única camada que um agente enxerga)

Regras:
  * K_DEFAULT: célula com menos de K pessoas é suprimida (vira vazio + flag).
  * K_DETAILED: cortes mais finos (empresa x departamento) usam um K maior.
  * Indicador sem dado é escrito como "n/a", nunca estimado nem deixado em branco sem explicação.
  * Não publicar o total junto do corte suprimido: a soma entrega a célula escondida.
"""
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[1] / "out"
BRONZE, GOLD = BASE / "bronze", BASE / "gold"
K_DEFAULT, K_DETAILED = 3, 5
NA = "n/a"


def suppress(df: pd.DataFrame, count_col: str, k: int) -> pd.DataFrame:
    out = df.copy()
    mask = out[count_col] < k
    out["suppressed"] = mask
    out.loc[mask, count_col] = pd.NA
    return out


def write(name: str, sheets: dict):
    GOLD.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(GOLD / f"{name}.xlsx") as xw:
        for sheet, df in sheets.items():
            df.to_excel(xw, sheet_name=sheet, index=False)


def headcount_by_department(hc):
    g = hc.groupby(["month", "company", "department"]).size().reset_index(name="headcount")
    write("Headcount - Department", {
        "data": suppress(g, "headcount", K_DETAILED),
        "dictionary": pd.DataFrame({
            "column": ["month", "company", "department", "headcount", "suppressed"],
            "meaning": ["first day of month", "legal entity", "department", "active people (CLT+PJ+other)",
                        f"True when fewer than {K_DETAILED} people"]}),
    })


def headcount_gender_core(hc):
    core = hc[hc["contract_type"].isin(["CLT", "PJ"])]  # visão padronizada: sem estágio/aprendiz
    g = core.groupby(["month", "company"]).agg(
        headcount=("employee_id", "size"),
        women=("gender", lambda s: (s == "F").sum())).reset_index()
    g["women_pct"] = (g["women"] / g["headcount"]).round(4)
    g = suppress(g, "headcount", K_DEFAULT)
    g.loc[g["suppressed"], ["women", "women_pct"]] = pd.NA
    write("Headcount - Gender (Core)", {"data": g})


def turnover_monthly(hc, ex):
    ex = ex.assign(month=ex["exit_date"].dt.to_period("M").dt.to_timestamp().dt.strftime("%Y-%m-%d"))
    e = ex.groupby(["month", "company", "initiative"]).size().unstack(fill_value=0).reset_index()
    for c in ("Employee", "Company"):
        if c not in e:
            e[c] = 0
    e["exits_total"] = e["Employee"] + e["Company"]
    h = hc.groupby(["month", "company"]).size().reset_index(name="headcount")
    t = h.merge(e, on=["month", "company"], how="left").fillna({"Employee": 0, "Company": 0, "exits_total": 0})
    t["turnover_pct"] = (t["exits_total"] / t["headcount"]).round(4)
    small = t["exits_total"] < K_DEFAULT  # poucos desligamentos: suprime e explica
    t["suppressed"] = small | (t["headcount"] < K_DETAILED)
    t.loc[t["suppressed"], ["Employee", "Company", "exits_total", "turnover_pct"]] = pd.NA
    t = t.rename(columns={"Employee": "exits_voluntary", "Company": "exits_involuntary"})
    write("Turnover - Monthly", {"data": t})
    return t


def time_to_hire(rq):
    done = rq.dropna(subset=["days_to_close"]).copy()
    done["closed_month"] = done["closed_date"].dt.to_period("M").dt.to_timestamp().dt.strftime("%Y-%m-%d")
    g = done.groupby(["closed_month", "company"]).agg(
        closed_reqs=("req_id", "size"), avg_days=("days_to_close", "mean")).reset_index()
    g["avg_days"] = g["avg_days"].round(1)
    g = suppress(g, "closed_reqs", K_DEFAULT)
    g.loc[g["suppressed"], "avg_days"] = pd.NA
    write("Time to Hire - Monthly", {"data": g})
    return g


def regrettable_turnover(ex, tl):
    """Talentos que saíram por iniciativa própria / total de saídas voluntárias (ponte ID -> chave)."""
    vol = ex[ex["initiative"] == "Employee"]
    talent_keys = set(tl["person_key"].dropna())
    g = vol.assign(is_talent=vol["person_key"].isin(talent_keys)).groupby("company").agg(
        voluntary_exits=("person_key", "size"), talent_exits=("is_talent", "sum")).reset_index()
    g["regrettable_pct"] = (g["talent_exits"] / g["voluntary_exits"]).round(4)
    g = suppress(g, "voluntary_exits", K_DETAILED)
    g.loc[g["suppressed"], ["talent_exits", "regrettable_pct"]] = pd.NA
    write("Regrettable Turnover", {"data": g})
    return g


def kpi_card(hc, turnover, tth, regret):
    """Arquivo-mestre: um card por empresa no último mês. O agente lê este, não os arquivos de apoio."""
    last = hc["month"].max()
    base = hc[hc["month"] == last].groupby("company").agg(
        headcount=("employee_id", "size"), women=("gender", lambda s: (s == "F").sum())).reset_index()
    base["women_pct"] = (base["women"] / base["headcount"]).round(4)
    t = turnover[turnover["month"] == last][["company", "turnover_pct"]]
    h = tth[tth["closed_month"] == last][["company", "avg_days"]].rename(columns={"avg_days": "time_to_hire_days"})
    r = regret[["company", "regrettable_pct"]]
    card = base.drop(columns="women").merge(t, on="company", how="left") \
        .merge(h, on="company", how="left").merge(r, on="company", how="left")
    card.insert(0, "month", last)
    card = card.fillna(NA)
    card["engagement_score"] = NA  # fonte ainda não disponível: declarado, não estimado
    write("KPI Card - Monthly", {"data": card})
    return card


def main():
    hc = pd.read_parquet(BRONZE / "headcount.parquet")
    ex = pd.read_parquet(BRONZE / "exits.parquet")
    rq = pd.read_parquet(BRONZE / "requisitions.parquet")
    tl = pd.read_parquet(BRONZE / "talent.parquet")

    headcount_by_department(hc)
    headcount_gender_core(hc)
    turnover = turnover_monthly(hc, ex)
    tth = time_to_hire(rq)
    regret = regrettable_turnover(ex, tl)
    card = kpi_card(hc, turnover, tth, regret)

    # Verificação: o Gold precisa reconciliar com o Bronze
    last = hc["month"].max()
    assert card["headcount"].sum() == (hc["month"] == last).sum(), "headcount do card não bate com o Bronze"
    gold_cols = set().union(*[set(pd.read_excel(p).columns) for p in GOLD.glob("*.xlsx")])
    assert not gold_cols & {"person_key", "employee_id", "source_file"}, "coluna de pessoa vazou para o Gold"
    print(f"Gold gravado em {GOLD} ({len(list(GOLD.glob('*.xlsx')))} arquivos). Verificações OK.")


if __name__ == "__main__":
    main()
