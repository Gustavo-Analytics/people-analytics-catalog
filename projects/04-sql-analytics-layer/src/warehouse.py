"""SQL layer: loads the Gold workbooks into DuckDB and exposes governed views and named queries.

Input : ../02-etl-consolidation-pattern/out/gold/*.xlsx  (run projects/02 first)
Layers: gold.*       raw copies of the Gold tables (suppressed cells are NULL)
        analytics.*  views over gold: the only schema a consumer should query

Usage : py projects/04-sql-analytics-layer/src/warehouse.py            # lists the queries
        py projects/04-sql-analytics-layer/src/warehouse.py privacy_audit
"""
import sys
from pathlib import Path

import duckdb
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
GOLD_DIR = HERE.parent / "02-etl-consolidation-pattern" / "out" / "gold"
VIEWS = HERE / "sql" / "views.sql"
QUERIES = HERE / "sql" / "queries"

# Gold workbook -> table name in the `gold` schema.
FILES = {
    "Turnover - Monthly.xlsx": "turnover",
    "Headcount - Department.xlsx": "headcount_dept",
    "Headcount - Gender (Core).xlsx": "headcount_gender",
    "Time to Hire - Monthly.xlsx": "time_to_hire",
    "Regrettable Turnover.xlsx": "regrettable",
    "KPI Card - Monthly.xlsx": "kpi",
}
DATE_COLUMNS = ("month", "closed_month")


def read_gold(gold_dir: Path = GOLD_DIR) -> dict[str, pd.DataFrame]:
    """Reads the `data` sheet of every Gold workbook into a dict keyed by table name."""
    missing = [name for name in FILES if not (gold_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"Gold not found ({missing[0]}); run projects/02 first")
    return {table: pd.read_excel(gold_dir / name, sheet_name="data") for name, table in FILES.items()}


def load(con: duckdb.DuckDBPyConnection, tables: dict[str, pd.DataFrame]) -> None:
    """Creates the `gold` tables and the `analytics` views on an open connection."""
    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    for name, frame in tables.items():
        frame = frame.astype(object).where(frame.notna(), None)  # NaN -> NULL, explicitly
        for col in DATE_COLUMNS:
            if col in frame.columns:
                frame[col] = pd.to_datetime(frame[col]).dt.date
        con.register("_frame", frame)
        con.execute(f"CREATE OR REPLACE TABLE gold.{name} AS SELECT * FROM _frame")
        con.unregister("_frame")
    con.execute(VIEWS.read_text(encoding="utf-8"))


def connect(gold_dir: Path = GOLD_DIR) -> duckdb.DuckDBPyConnection:
    """Returns an in-memory DuckDB with Gold loaded and the governed views created."""
    con = duckdb.connect(":memory:")
    load(con, read_gold(gold_dir))
    return con


def query_names() -> list[str]:
    """Names of the stored queries (the file names in sql/queries, without extension)."""
    return sorted(p.stem for p in QUERIES.glob("*.sql"))


def run_query(con: duckdb.DuckDBPyConnection, name: str) -> pd.DataFrame:
    """Runs a stored query by name and returns the result as a DataFrame."""
    if name not in query_names():
        raise KeyError(f"unknown query '{name}'; available: {', '.join(query_names())}")
    return con.execute((QUERIES / f"{name}.sql").read_text(encoding="utf-8")).df()


def main(argv: list[str]) -> int:
    """CLI: with no argument lists the queries; with a name prints its result.

    Exit codes: 0 ok, 1 the privacy audit found violations, 2 unknown query or Gold missing.
    """
    if not argv:
        print("Stored queries:", *query_names(), sep="\n  ")
        return 0
    try:
        result = run_query(connect(), argv[0])
    except (KeyError, FileNotFoundError) as err:
        print(f"error: {err.args[0]}", file=sys.stderr)
        return 2
    print(result.to_string(index=False) if len(result) else "(no rows)")
    return 1 if argv[0] == "privacy_audit" and len(result) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
