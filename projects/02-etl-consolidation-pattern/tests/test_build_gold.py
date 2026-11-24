"""Tests of the Gold layer: k-anonymity, standardized views, rates, "n/a" and the no-person-column rule."""
import contextlib
import io
import sys
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import build_gold  # noqa: E402

K_DEFAULT, K_DETAILED = build_gold.K_DEFAULT, build_gold.K_DETAILED
JAN, FEB = "2026-01-01", "2026-02-01"
PERSON_COLUMNS = {"person_key", "employee_id", "source_file"}


@contextlib.contextmanager
def gold_dir() -> Iterator[Path]:
    """Writes Gold files to a temporary folder and silences the module's log lines."""
    with tempfile.TemporaryDirectory() as d:
        with mock.patch.object(build_gold, "GOLD", Path(d)), contextlib.redirect_stdout(io.StringIO()):
            yield Path(d)


def read(folder: Path, name: str, sheet: str = "data") -> pd.DataFrame:
    """Reads one sheet of a Gold workbook."""
    return pd.read_excel(folder / f"{name}.xlsx", sheet_name=sheet)


def people(n: int, company: str, month: str = JAN, contract: str = "CLT", gender: str = "F",
           dept: str = "Ops", start: int = 0) -> list[dict[str, str]]:
    """`n` headcount rows for one company and month."""
    return [{"month": month, "employee_id": f"{company}-{month}-{contract}-{gender}-{start + i}",
             "person_key": f"{start + i:011d}", "company": company, "department": dept,
             "contract_type": contract, "gender": gender, "seniority": "Mid", "source_file": "x.csv"}
            for i in range(n)]


def exits(n: int, company: str, initiative: str, date: str = "2026-01-15", first_key: int = 0) -> pd.DataFrame:
    """`n` terminations of one company with the given initiative ('Employee' or 'Company')."""
    return pd.DataFrame({"person_key": [f"{first_key + i:011d}" for i in range(n)], "employee_id": "0",
                         "company": company, "exit_date": pd.to_datetime(date), "initiative": initiative,
                         "reason": "r", "source_file": "x.csv"})


class SuppressTests(unittest.TestCase):
    def test_counts_below_k_are_emptied_and_flagged(self) -> None:
        out = build_gold.suppress(pd.DataFrame({"n": [2, 3, 10]}), "n", 3)
        self.assertEqual(out["suppressed"].tolist(), [True, False, False])
        self.assertEqual(out["n"].isna().tolist(), [True, False, False])
        self.assertEqual(out.loc[~out["suppressed"], "n"].tolist(), [3, 10])

    def test_does_not_change_its_input(self) -> None:
        df = pd.DataFrame({"n": [1, 5]})
        build_gold.suppress(df, "n", 3)
        self.assertEqual(df["n"].tolist(), [1, 5])
        self.assertNotIn("suppressed", df.columns)

    @settings(max_examples=100, deadline=None, database=None, suppress_health_check=[HealthCheck.too_slow])
    @given(st.lists(st.integers(min_value=0, max_value=200), min_size=1, max_size=40),
           st.integers(min_value=1, max_value=12))
    def test_property_only_counts_at_or_above_k_survive(self, counts: list[int], k: int) -> None:
        out = build_gold.suppress(pd.DataFrame({"n": counts}), "n", k)
        self.assertEqual(out["suppressed"].tolist(), [c < k for c in counts])
        self.assertEqual(out.loc[~out["suppressed"], "n"].tolist(), [c for c in counts if c >= k])


class HeadcountTests(unittest.TestCase):
    def test_core_view_excludes_interns_and_counts_women(self) -> None:
        groups = [(3, "CLT", "F", 0), (3, "CLT", "M", 10), (1, "PJ", "F", 20), (1, "PJ", "M", 30),
                  (4, "Intern", "F", 40)]
        hc = pd.DataFrame([row for n, contract, gender, start in groups
                           for row in people(n, "Acme A", contract=contract, gender=gender, start=start)])
        with gold_dir() as d:
            build_gold.headcount_gender_core(hc)
            row = read(d, "Headcount - Gender (Core)").iloc[0]
        self.assertEqual(row["headcount"], 8)  # 4 interns are not part of the standardized view
        self.assertEqual(row["women"], 4)
        self.assertEqual(row["women_pct"], 0.5)
        self.assertFalse(row["suppressed"])

    def test_small_company_is_suppressed(self) -> None:
        hc = pd.DataFrame(people(K_DEFAULT - 1, "Acme B"))
        with gold_dir() as d:
            build_gold.headcount_gender_core(hc)
            row = read(d, "Headcount - Gender (Core)").iloc[0]
        self.assertTrue(row["suppressed"])
        self.assertTrue(pd.isna(row["headcount"]) and pd.isna(row["women_pct"]))

    def test_department_cut_uses_the_larger_k(self) -> None:
        hc = pd.DataFrame(people(K_DETAILED, "Acme A", dept="Ops")
                          + people(K_DETAILED - 1, "Acme A", dept="Fin", start=100))
        with gold_dir() as d:
            build_gold.headcount_by_department(hc)
            data = read(d, "Headcount - Department").set_index("department")
            dictionary = read(d, "Headcount - Department", sheet="dictionary")
        self.assertFalse(data.loc["Ops", "suppressed"])
        self.assertTrue(data.loc["Fin", "suppressed"])
        self.assertEqual(len(dictionary), 5)  # the data dictionary is published with the data


class TurnoverTests(unittest.TestCase):
    def test_rate_and_voluntary_split(self) -> None:
        hc = pd.DataFrame(people(20, "Acme A"))
        ex = pd.concat([exits(2, "Acme A", "Employee"), exits(2, "Acme A", "Company", first_key=10)])
        with gold_dir():
            t = build_gold.turnover_monthly(hc, ex)
        row = t.iloc[0]
        self.assertEqual((row["exits_voluntary"], row["exits_involuntary"], row["exits_total"]), (2, 2, 4))
        self.assertEqual(row["turnover_pct"], 0.2)  # 4 exits over 20 people
        self.assertFalse(row["suppressed"])

    def test_few_exits_and_months_without_exits_are_suppressed(self) -> None:
        hc = pd.DataFrame(people(10, "Acme B") + people(10, "Acme B", month=FEB, start=100))
        ex = exits(K_DEFAULT - 1, "Acme B", "Employee")  # January only, below K
        with gold_dir():
            t = build_gold.turnover_monthly(hc, ex).set_index("month")
        self.assertTrue(t.loc[JAN, "suppressed"])
        self.assertTrue(t.loc[FEB, "suppressed"])  # no exits at all: the count 0 is below K as well
        self.assertTrue(pd.isna(t.loc[JAN, "turnover_pct"]))


class TimeToHireTests(unittest.TestCase):
    def test_average_by_closing_month_and_suppression(self) -> None:
        def req(rid: str, company: str, days: float | None) -> dict[str, object]:
            closed = pd.Timestamp("2026-01-20") if days is not None else pd.NaT
            return {"req_id": rid, "company": company, "closed_date": closed, "days_to_close": days}

        rq = pd.DataFrame([req("1", "Acme A", 10), req("2", "Acme A", 20), req("3", "Acme A", 30),
                           req("4", "Acme B", 5), req("5", "Acme A", None)])  # R5 is still open
        with gold_dir():
            g = build_gold.time_to_hire(rq).set_index("company")
        self.assertEqual((g.loc["Acme A", "closed_reqs"], g.loc["Acme A", "avg_days"]), (3, 20.0))
        self.assertTrue(g.loc["Acme B", "suppressed"])
        self.assertTrue(pd.isna(g.loc["Acme B", "avg_days"]))


class RegrettableTurnoverTests(unittest.TestCase):
    def test_share_of_talent_among_voluntary_exits_only(self) -> None:
        voluntary_a = exits(6, "Acme A", "Employee")  # keys 0..5
        involuntary_a = exits(2, "Acme A", "Company", first_key=50)  # never counted
        voluntary_b = exits(2, "Acme B", "Employee", first_key=100)  # below K_DETAILED
        ex = pd.concat([voluntary_a, involuntary_a, voluntary_b])
        talent = pd.DataFrame({"person_key": ["00000000000", "00000000001", None]})  # two talent, one unmatched
        with gold_dir():
            g = build_gold.regrettable_turnover(ex, talent).set_index("company")
        self.assertEqual((g.loc["Acme A", "voluntary_exits"], g.loc["Acme A", "talent_exits"]), (6, 2))
        self.assertAlmostEqual(g.loc["Acme A", "regrettable_pct"], 2 / 6, places=4)
        self.assertTrue(g.loc["Acme B", "suppressed"])


class KpiCardTests(unittest.TestCase):
    def test_missing_indicators_are_declared_not_estimated(self) -> None:
        hc = pd.DataFrame(people(10, "Acme A", month=FEB) + people(4, "Acme B", month=FEB, start=100))
        turnover = pd.DataFrame({"month": [FEB], "company": ["Acme A"], "turnover_pct": [0.05]})
        tth = pd.DataFrame({"closed_month": [FEB], "company": ["Acme A"], "avg_days": [20.0]})
        regret = pd.DataFrame({"company": ["Acme A", "Acme B"], "regrettable_pct": [0.1, None]})
        with gold_dir():
            card = build_gold.kpi_card(hc, turnover, tth, regret).set_index("company")
        self.assertEqual(card.loc["Acme A", "time_to_hire_days"], 20.0)
        for column in ("turnover_pct", "time_to_hire_days", "regrettable_pct"):
            self.assertEqual(card.loc["Acme B", column], build_gold.NA)
        self.assertTrue((card["engagement_score"] == build_gold.NA).all())  # no source yet: declared, not estimated


class EndToEndTests(unittest.TestCase):
    @staticmethod
    def write_bronze(folder: Path) -> None:
        """Minimal Bronze layer: two months, one large and one small company."""
        hc = pd.DataFrame(people(12, "Acme A") + people(3, "Acme B", start=100)
                          + people(12, "Acme A", month=FEB) + people(3, "Acme B", month=FEB, start=100))
        ex = pd.concat([exits(2, "Acme A", "Employee", date="2026-02-10"),
                        exits(2, "Acme A", "Company", date="2026-02-12", first_key=10)])
        rq = pd.DataFrame({"req_id": ["1", "2", "3"], "company": "Acme A", "department": "Ops",
                           "opened_date": pd.to_datetime("2026-01-05"), "closed_date": pd.to_datetime("2026-02-04"),
                           "source": "External", "days_to_close": 30})
        talent = pd.DataFrame({"employee_id": ["x"], "cycle": ["C1"], "person_key": ["00000000000"]})
        for name, df in [("headcount", hc), ("exits", ex), ("requisitions", rq), ("talent", talent)]:
            df.to_parquet(folder / f"{name}.parquet", index=False)

    def test_main_builds_every_file_and_leaks_no_person_column(self) -> None:
        with tempfile.TemporaryDirectory() as b, gold_dir() as g:
            self.write_bronze(Path(b))
            with mock.patch.object(build_gold, "BRONZE", Path(b)):
                build_gold.main()
            files = sorted(p.name for p in g.glob("*.xlsx"))
            columns = set().union(*[set(pd.read_excel(p).columns) for p in g.glob("*.xlsx")])
        self.assertEqual(len(files), 6)
        self.assertEqual(columns & PERSON_COLUMNS, set())

    def test_main_stops_if_a_person_column_reaches_gold(self) -> None:
        def leaky(hc: pd.DataFrame) -> None:
            build_gold.write("Leaky", {"data": pd.DataFrame({"person_key": ["x"]})})

        with tempfile.TemporaryDirectory() as b, gold_dir():
            self.write_bronze(Path(b))
            with mock.patch.object(build_gold, "BRONZE", Path(b)), \
                    mock.patch.object(build_gold, "headcount_by_department", leaky):
                with self.assertRaises(AssertionError):
                    build_gold.main()


if __name__ == "__main__":
    unittest.main()
