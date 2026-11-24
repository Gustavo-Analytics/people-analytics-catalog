"""Tests of loading the Gold tables, ISO period parsing and the "generated code cannot change the data" rule."""
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import assistant  # noqa: E402
from periods import parse_period  # noqa: E402
from test_assistant import make_tables  # noqa: E402


def write_gold(folder: Path, month_as_date: bool = False) -> None:
    """Writes the five Gold workbooks the assistant reads, with a single row each."""
    month: object = pd.Timestamp("2026-01-01") if month_as_date else "2026-01-01"
    frames = {
        "headcount": pd.DataFrame({"month": [month], "company": ["Acme A"], "headcount": [10]}),
        "turnover": pd.DataFrame({"month": [month], "company": ["Acme A"], "turnover_pct": [0.05]}),
        "tth": pd.DataFrame({"closed_month": [month], "company": ["Acme A"], "avg_days": [20.0]}),
        "regret": pd.DataFrame({"company": ["Acme A"], "regrettable_pct": [0.1]}),
        "kpi": pd.DataFrame({"month": [month], "company": ["Acme A"]}),
    }
    for key, name in assistant.FILES.items():
        frames[key].to_excel(folder / name, index=False)


class LoadTablesTests(unittest.TestCase):
    def test_loads_every_table_and_normalizes_the_month_column(self) -> None:
        for as_date in (False, True):
            with self.subTest(month_as_date=as_date), tempfile.TemporaryDirectory() as d:
                write_gold(Path(d), month_as_date=as_date)
                tables = assistant.load_tables(d)
            self.assertEqual(set(tables), set(assistant.FILES))
            self.assertEqual(tables["headcount"]["month"].tolist(), ["2026-01-01"])
            self.assertEqual(tables["tth"]["month"].tolist(), ["2026-01-01"])  # closed_month was renamed
            self.assertNotIn("closed_month", tables["tth"].columns)

    def test_a_missing_file_points_to_the_project_that_builds_it(self) -> None:
        with tempfile.TemporaryDirectory() as d, self.assertRaises(FileNotFoundError) as raised:
            assistant.load_tables(d)
        self.assertIn("project 02", str(raised.exception))


class PeriodTests(unittest.TestCase):
    MONTHS = ["2026-08-01", "2026-09-01", "2026-10-01"]

    def test_iso_month_is_understood(self) -> None:
        self.assertEqual(parse_period("em 2026-09", self.MONTHS), ("2026-09-01", "ok"))

    def test_iso_month_outside_the_series_is_out_of_range(self) -> None:
        self.assertEqual(parse_period("em 2026-13", self.MONTHS)[1], "out_of_range")
        self.assertEqual(parse_period("em 2025-01", self.MONTHS)[1], "out_of_range")

    def test_previous_month_needs_at_least_two_months(self) -> None:
        self.assertEqual(parse_period("mês passado", ["2026-10-01"]), (None, "out_of_range"))


class AnswerTests(unittest.TestCase):
    def test_a_company_without_a_row_for_the_month_is_reported_as_no_data(self) -> None:
        text = assistant.answer("Time to hire da Acme B", make_tables()).text
        self.assertIn("- Acme B: sem dado no período", text)

    def test_generated_code_cannot_change_the_loaded_data(self) -> None:
        tables = make_tables()
        before = tables["headcount"]["headcount"].tolist()

        def codegen(question: str, schema: dict[str, list[str]]) -> str:
            return "headcount['headcount'] = 0\nresult = int(headcount['headcount'].sum())"

        result = assistant.stage2("qualquer pergunta", tables, codegen)
        assert result is not None
        self.assertIn("0", result.text)  # the code did run and zeroed its own copy
        self.assertEqual(tables["headcount"]["headcount"].tolist(), before)  # the original is untouched

    def test_stage_two_gives_up_when_the_code_is_rejected(self) -> None:
        def codegen(question: str, schema: dict[str, list[str]]) -> str:
            return "import os\nresult = 1"

        self.assertIsNone(assistant.stage2("qualquer pergunta", make_tables(), codegen))


if __name__ == "__main__":
    unittest.main()
