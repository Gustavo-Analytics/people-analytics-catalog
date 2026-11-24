"""Tests of the SQL layer: views, stored queries, NULL handling and the privacy audit."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import warehouse  # noqa: E402

NAN = float("nan")


def tables() -> dict[str, pd.DataFrame]:
    """A small, valid Gold: two companies over four months; B is suppressed in the first two."""
    months = ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"]
    turnover = pd.DataFrame({
        "month": months * 2,
        "company": ["A"] * 4 + ["B"] * 4,
        "headcount": [100, 110, 99, 99, 20, 20, 21, 22],
        "exits_involuntary": [1, 1, 1, 1, NAN, NAN, 1, 1],
        "exits_voluntary": [3, 5, 3, 3, NAN, NAN, 2, 3],
        "exits_total": [4, 6, 4, 4, NAN, NAN, 3, 4],
        "turnover_pct": [0.04, 0.0545, 0.0404, 0.0404, NAN, NAN, 0.1429, 0.1818],
        "suppressed": [False, False, False, False, True, True, False, False],
    })
    dept = pd.DataFrame({"month": ["2026-01-01"] * 2, "company": ["A", "B"], "department": ["X", "X"],
                         "headcount": [50, NAN], "suppressed": [False, True]})
    gender = pd.DataFrame({"month": ["2026-01-01"] * 2, "company": ["A", "B"], "headcount": [100, NAN],
                           "women": [40, NAN], "women_pct": [0.4, NAN], "suppressed": [False, True]})
    tth = pd.DataFrame({"closed_month": ["2026-01-01"] * 2, "company": ["A", "B"], "closed_reqs": [4, NAN],
                        "avg_days": [30.0, NAN], "suppressed": [False, True]})
    regret = pd.DataFrame({"company": ["A", "B"], "voluntary_exits": [10, NAN], "talent_exits": [2, NAN],
                           "regrettable_pct": [0.2, NAN], "suppressed": [False, True]})
    kpi = pd.DataFrame({"month": ["2026-04-01"], "company": ["A"], "headcount": [99], "women_pct": [0.4],
                        "turnover_pct": [0.0404], "time_to_hire_days": [30.0], "regrettable_pct": [0.2],
                        "engagement_score": ["n/a"]})
    return {"turnover": turnover, "headcount_dept": dept, "headcount_gender": gender,
            "time_to_hire": tth, "regrettable": regret, "kpi": kpi}


def connect(data: dict[str, pd.DataFrame] | None = None) -> duckdb.DuckDBPyConnection:
    """Builds an in-memory warehouse from the given (or the default) tables."""
    con = duckdb.connect(":memory:")
    warehouse.load(con, data if data is not None else tables())
    return con


class TestLoading(unittest.TestCase):
    """Gold becomes tables with real NULLs and real dates."""

    def test_suppressed_cells_are_null_not_nan(self) -> None:
        con = connect()
        n = con.execute("SELECT count(*) FROM gold.turnover WHERE suppressed AND turnover_pct IS NULL").fetchone()
        self.assertEqual(n, (2,))

    def test_month_is_a_date(self) -> None:
        kind = connect().execute("SELECT typeof(month) FROM gold.turnover LIMIT 1").fetchone()
        self.assertEqual(kind, ("DATE",))

    def test_all_gold_tables_exist(self) -> None:
        names = {r[0] for r in connect().execute("SELECT table_name FROM information_schema.tables "
                                                 "WHERE table_schema = 'gold'").fetchall()}
        self.assertEqual(names, set(warehouse.FILES.values()))


class TestViews(unittest.TestCase):
    """Window functions ignore suppressed values and never invent them."""

    def test_headcount_mom(self) -> None:
        row = connect().execute("SELECT change, change_pct FROM analytics.headcount_mom "
                                "WHERE company = 'A' AND month = DATE '2026-02-01'").fetchone()
        self.assertEqual(row, (10, 10.0))

    def test_first_month_has_no_change(self) -> None:
        row = connect().execute("SELECT change FROM analytics.headcount_mom "
                                "WHERE company = 'A' AND month = DATE '2026-01-01'").fetchone()
        self.assertEqual(row, (None,))

    def test_rolling_average_skips_suppressed_months(self) -> None:
        # B: Mar = 0.1429, Apr = 0.1818 with Jan/Feb suppressed -> the average of the 2 published months.
        row = connect().execute("SELECT turnover_3m_avg, months_with_data FROM analytics.turnover_rolling "
                                "WHERE company = 'B' AND month = DATE '2026-04-01'").fetchone()
        assert row is not None
        self.assertAlmostEqual(row[0], (0.1429 + 0.1818) / 2, places=4)
        self.assertEqual(row[1], 2)

    def test_rolling_average_is_null_when_every_month_is_suppressed(self) -> None:
        row = connect().execute("SELECT turnover_3m_avg, months_with_data FROM analytics.turnover_rolling "
                                "WHERE company = 'B' AND month = DATE '2026-02-01'").fetchone()
        self.assertEqual(row, (None, 0))


class TestQueries(unittest.TestCase):
    """Stored queries return what they promise."""

    def test_ranking_is_dense_in_position_and_uses_the_latest_month(self) -> None:
        df = warehouse.run_query(connect(), "turnover_ranking")
        self.assertEqual(list(df["company"]), ["B", "A"])
        self.assertEqual(list(df["position"]), [1, 2])  # one row per company, no gaps
        self.assertEqual(list(df["turnover_pct"]), [18.18, 4.04])

    def test_ranking_omits_a_company_that_is_fully_suppressed(self) -> None:
        data = tables()
        t = data["turnover"]
        t.loc[t["company"] == "B", ["exits_total", "turnover_pct"]] = NAN
        t.loc[t["company"] == "B", "suppressed"] = True
        df = warehouse.run_query(connect(data), "turnover_ranking")
        self.assertEqual(list(df["company"]), ["A"])

    def test_headcount_trend_returns_at_most_three_months_per_company(self) -> None:
        df = warehouse.run_query(connect(), "headcount_trend")
        self.assertEqual(df.groupby("company").size().to_dict(), {"A": 3, "B": 3})

    def test_rolling_query_requires_two_published_months(self) -> None:
        df = warehouse.run_query(connect(), "turnover_rolling")
        self.assertEqual(df[df["company"] == "B"]["months_with_data"].min(), 2)

    def test_unknown_query_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            warehouse.run_query(connect(), "drop_everything")

    def test_query_name_cannot_escape_the_folder(self) -> None:
        with self.assertRaises(KeyError):
            warehouse.run_query(connect(), "../views")


class TestPrivacyAudit(unittest.TestCase):
    """The audit view is empty on a healthy Gold and flags each way of breaking k-anonymity."""

    def violations(self, data: dict[str, pd.DataFrame]) -> list[tuple[str, str]]:
        rows = connect(data).execute("SELECT table_name, rule FROM analytics.privacy_violations").fetchall()
        return [(r[0], r[1]) for r in rows]

    def test_healthy_gold_has_no_violations(self) -> None:
        self.assertEqual(self.violations(tables()), [])

    def test_published_small_department_is_flagged(self) -> None:
        data = tables()
        data["headcount_dept"].loc[0, "headcount"] = 4
        self.assertIn(("headcount_dept", "published count below k=5"), self.violations(data))

    def test_suppressed_row_that_still_has_a_value_is_flagged(self) -> None:
        data = tables()
        data["headcount_gender"].loc[1, "headcount"] = 2
        self.assertIn(("headcount_gender", "suppressed row still carries a value"), self.violations(data))

    def test_turnover_with_few_exits_is_flagged(self) -> None:
        data = tables()
        data["turnover"].loc[0, "exits_total"] = 2
        found = self.violations(data)
        self.assertEqual([t for t, _ in found], ["turnover"])

    def test_time_to_hire_and_regrettable_are_audited(self) -> None:
        data = tables()
        data["time_to_hire"].loc[0, "closed_reqs"] = 2
        data["regrettable"].loc[0, "voluntary_exits"] = 4
        self.assertEqual({t for t, _ in self.violations(data)}, {"time_to_hire", "regrettable"})


class TestCli(unittest.TestCase):
    """The command line wrapper: exit codes and messages."""

    def run_main(self, argv: list[str], data: dict[str, pd.DataFrame] | None = None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with (mock.patch.object(warehouse, "connect", lambda: connect(data)),
              contextlib.redirect_stdout(out), contextlib.redirect_stderr(err)):
            code = warehouse.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_no_argument_lists_the_queries(self) -> None:
        code, out, _ = self.run_main([])
        self.assertEqual(code, 0)
        self.assertIn("privacy_audit", out)

    def test_runs_a_query(self) -> None:
        code, out, _ = self.run_main(["turnover_ranking"])
        self.assertEqual(code, 0)
        self.assertIn("position", out)

    def test_unknown_query_exits_with_2(self) -> None:
        code, _, err = self.run_main(["nope"])
        self.assertEqual(code, 2)
        self.assertIn("unknown query", err)

    def test_audit_exits_1_when_there_are_violations(self) -> None:
        data = tables()
        data["headcount_dept"].loc[0, "headcount"] = 4
        code, out, _ = self.run_main(["privacy_audit"], data)
        self.assertEqual(code, 1)
        self.assertIn("headcount_dept", out)

    def test_audit_prints_no_rows_and_exits_0_on_healthy_gold(self) -> None:
        code, out, _ = self.run_main(["privacy_audit"])
        self.assertEqual((code, out.strip()), (0, "(no rows)"))


class TestReadGold(unittest.TestCase):
    """Reading the Gold workbooks from disk."""

    def test_missing_gold_explains_what_to_run(self) -> None:
        with tempfile.TemporaryDirectory() as d, self.assertRaises(FileNotFoundError) as ctx:
            warehouse.read_gold(Path(d))
        self.assertIn("run projects/02 first", str(ctx.exception))

    def test_reads_the_data_sheet_of_each_workbook(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            for name, table in warehouse.FILES.items():
                with pd.ExcelWriter(Path(d) / name) as xw:
                    tables()[table].to_excel(xw, sheet_name="data", index=False)
                    pd.DataFrame({"column": ["x"]}).to_excel(xw, sheet_name="dictionary", index=False)
            read = warehouse.read_gold(Path(d))
        self.assertEqual(set(read), set(warehouse.FILES.values()))
        self.assertEqual(len(read["turnover"]), 8)

    def test_connect_builds_the_warehouse_from_files(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            for name, table in warehouse.FILES.items():
                with pd.ExcelWriter(Path(d) / name) as xw:
                    tables()[table].to_excel(xw, sheet_name="data", index=False)
            con = warehouse.connect(Path(d))
        self.assertEqual(con.execute("SELECT count(*) FROM analytics.privacy_violations").fetchone(), (0,))


if __name__ == "__main__":
    unittest.main()
