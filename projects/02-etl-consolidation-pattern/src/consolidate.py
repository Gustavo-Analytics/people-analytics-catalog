"""Bronze layer: consolidates monthly files, normalizes keys and removes duplicates.

Input : synthetic-data/sample/{headcount,exits}/*.csv, requisitions.csv, talent_calibration.csv
Output: out/bronze/*.parquet (nominal; never published nor connected to an agent)

Lessons applied here:
  1. Read everything as text (dtype=str). If the reader infers a number, "03573322108" becomes 3573322108.
  2. Normalize the key on BOTH sides of the join (zfill) before joining, or the join fails silently.
  3. Deduplicate on the business key and record how many rows were dropped (audit).
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "synthetic-data" / "sample"
BRONZE = Path(__file__).resolve().parents[1] / "out" / "bronze"


def norm_key(s: pd.Series) -> pd.Series:
    """Keeps digits only and restores the leading zero (11-digit key)."""
    return s.astype("string").str.replace(r"\D", "", regex=True).str.zfill(11)


def read_many(folder: Path) -> pd.DataFrame:
    """Reads every CSV of a folder as text and records the origin file in `source_file`."""
    frames = []
    for f in sorted(folder.glob("*.csv")):
        df = pd.read_csv(f, dtype=str)
        df["source_file"] = f.name
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def build_headcount() -> pd.DataFrame:
    """Consolidates the monthly headcount files; one row per employee and month."""
    df = read_many(SAMPLE / "headcount")
    df["person_key"] = norm_key(df["person_key"])
    for c in ["company", "department", "contract_type", "gender", "seniority"]:
        df[c] = df[c].str.strip()
    before = len(df)
    df = df.drop_duplicates(subset=["month", "employee_id"], keep="last")
    print(f"headcount : {before} -> {len(df)} rows ({before - len(df)} duplicates removed)")
    return df


def build_exits() -> pd.DataFrame:
    """Consolidates the termination reports, dropping the repeats of cumulative reports."""
    df = read_many(SAMPLE / "exits")
    df["person_key"] = norm_key(df["person_key"])
    df["exit_date"] = pd.to_datetime(df["exit_date"])
    before = len(df)
    # cumulative reports repeat terminations: the business key is person + date
    df = df.sort_values("source_file").drop_duplicates(subset=["person_key", "exit_date"], keep="last")
    print(f"exits     : {before} -> {len(df)} rows ({before - len(df)} duplicates removed)")
    return df


def build_requisitions() -> pd.DataFrame:
    """Reads the requisitions and computes the days between opening and closing."""
    df = pd.read_csv(SAMPLE / "requisitions.csv", dtype=str)
    df["opened_date"] = pd.to_datetime(df["opened_date"])
    df["closed_date"] = pd.to_datetime(df["closed_date"])
    df["days_to_close"] = (df["closed_date"] - df["opened_date"]).dt.days
    return df


def build_talent_bridge(headcount: pd.DataFrame) -> pd.DataFrame:
    """ID -> person key bridge. The talent list only carries the employee ID."""
    talent = pd.read_csv(SAMPLE / "talent_calibration.csv", dtype=str)
    bridge = headcount[["employee_id", "person_key"]].drop_duplicates("employee_id")
    out = talent.merge(bridge, on="employee_id", how="left")
    miss = out["person_key"].isna().sum()
    print(f"talent    : {len(out)} rows, {miss} without a match in headcount")
    return out


def main() -> None:
    """Builds the four Bronze tables and writes them as parquet."""
    BRONZE.mkdir(parents=True, exist_ok=True)
    hc = build_headcount()
    ex = build_exits()
    rq = build_requisitions()
    tl = build_talent_bridge(hc)
    for name, df in [("headcount", hc), ("exits", ex), ("requisitions", rq), ("talent", tl)]:
        df.to_parquet(BRONZE / f"{name}.parquet", index=False)
    print(f"Bronze written to {BRONZE}")


if __name__ == "__main__":
    main()
