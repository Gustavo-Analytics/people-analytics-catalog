"""Camada Bronze: consolida arquivos mensais, normaliza chaves e remove duplicatas.

Entrada : synthetic-data/sample/{headcount,exits}/*.csv, requisitions.csv, talent_calibration.csv
Saída   : out/bronze/*.parquet (nominal; nunca é publicado nem conectado a um agente)

Lições aplicadas aqui:
  1. Ler tudo como texto (dtype=str). Se o leitor inferir número, "03573322108" vira 3573322108.
  2. Normalizar a chave nos DOIS lados do join (zfill) antes de cruzar, senão o join falha em silêncio.
  3. Deduplicar por chave de negócio e registrar quantas linhas saíram (auditoria).
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "synthetic-data" / "sample"
BRONZE = Path(__file__).resolve().parents[1] / "out" / "bronze"


def norm_key(s: pd.Series) -> pd.Series:
    """Deixa só dígitos e restaura o zero à esquerda (chave de 11 dígitos)."""
    return s.astype("string").str.replace(r"\D", "", regex=True).str.zfill(11)


def read_many(folder: Path) -> pd.DataFrame:
    frames = []
    for f in sorted(folder.glob("*.csv")):
        df = pd.read_csv(f, dtype=str)
        df["source_file"] = f.name
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def build_headcount() -> pd.DataFrame:
    df = read_many(SAMPLE / "headcount")
    df["person_key"] = norm_key(df["person_key"])
    for c in ["company", "department", "contract_type", "gender", "seniority"]:
        df[c] = df[c].str.strip()
    before = len(df)
    df = df.drop_duplicates(subset=["month", "employee_id"], keep="last")
    print(f"headcount : {before} -> {len(df)} linhas ({before - len(df)} duplicadas removidas)")
    return df


def build_exits() -> pd.DataFrame:
    df = read_many(SAMPLE / "exits")
    df["person_key"] = norm_key(df["person_key"])
    df["exit_date"] = pd.to_datetime(df["exit_date"])
    before = len(df)
    # relatórios cumulativos repetem desligamentos: a chave de negócio é pessoa + data
    df = df.sort_values("source_file").drop_duplicates(subset=["person_key", "exit_date"], keep="last")
    print(f"exits     : {before} -> {len(df)} linhas ({before - len(df)} duplicadas removidas)")
    return df


def build_requisitions() -> pd.DataFrame:
    df = pd.read_csv(SAMPLE / "requisitions.csv", dtype=str)
    df["opened_date"] = pd.to_datetime(df["opened_date"])
    df["closed_date"] = pd.to_datetime(df["closed_date"])
    df["days_to_close"] = (df["closed_date"] - df["opened_date"]).dt.days
    return df


def build_talent_bridge(headcount: pd.DataFrame) -> pd.DataFrame:
    """Ponte ID -> chave da pessoa. A lista de talentos só traz o ID do funcionário."""
    talent = pd.read_csv(SAMPLE / "talent_calibration.csv", dtype=str)
    bridge = headcount[["employee_id", "person_key"]].drop_duplicates("employee_id")
    out = talent.merge(bridge, on="employee_id", how="left")
    miss = out["person_key"].isna().sum()
    print(f"talentos  : {len(out)} linhas, {miss} sem correspondência no headcount")
    return out


def main():
    BRONZE.mkdir(parents=True, exist_ok=True)
    hc = build_headcount()
    ex = build_exits()
    rq = build_requisitions()
    tl = build_talent_bridge(hc)
    for name, df in [("headcount", hc), ("exits", ex), ("requisitions", rq), ("talent", tl)]:
        df.to_parquet(BRONZE / f"{name}.parquet", index=False)
    print(f"Bronze gravado em {BRONZE}")


if __name__ == "__main__":
    main()
