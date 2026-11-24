"""Tests of the Bronze layer: key normalization, consolidation, deduplication and the ID -> key bridge."""
import contextlib
import io
import sys
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import consolidate  # noqa: E402


@contextlib.contextmanager
def sample_dir() -> Iterator[Path]:
    """Points the module at a temporary sample folder and silences its log lines."""
    with tempfile.TemporaryDirectory() as d:
        with mock.patch.object(consolidate, "SAMPLE", Path(d)), contextlib.redirect_stdout(io.StringIO()):
            yield Path(d)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    """Writes rows as a CSV file, creating the folder if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def hc_row(month: str, employee: str, key: str, company: str = "Acme A") -> dict[str, str]:
    """One headcount row with the columns the Bronze step expects."""
    return {"month": month, "employee_id": employee, "person_key": key, "company": company,
            "department": "Ops", "contract_type": "CLT", "gender": "F", "seniority": "Mid"}


def exit_row(key: str, date: str, company: str = "Acme A") -> dict[str, str]:
    """One termination row with the columns the Bronze step expects."""
    return {"person_key": key, "employee_id": "1", "company": company, "exit_date": date,
            "initiative": "Employee", "reason": "Better offer"}


class NormKeyTests(unittest.TestCase):
    def test_restores_the_leading_zero(self) -> None:
        self.assertEqual(consolidate.norm_key(pd.Series(["3573322108"])).tolist(), ["03573322108"])

    def test_strips_formatting(self) -> None:
        self.assertEqual(consolidate.norm_key(pd.Series(["035.733.221-08"])).tolist(), ["03573322108"])

    def test_keeps_a_complete_key(self) -> None:
        self.assertEqual(consolidate.norm_key(pd.Series(["12345678901"])).tolist(), ["12345678901"])

    def test_number_style_and_padded_style_become_the_same_key(self) -> None:
        a, b = consolidate.norm_key(pd.Series(["3573322108", "03573322108"]))
        self.assertEqual(a, b)

    def test_missing_value_stays_missing(self) -> None:
        self.assertEqual(consolidate.norm_key(pd.Series([None, "5"])).isna().tolist(), [True, False])


class ReadManyTests(unittest.TestCase):
    def test_reads_as_text_and_records_the_origin_file(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "b.csv").write_text("person_key,month\n00123456789,2026-02-01\n", encoding="utf-8")
            (Path(d) / "a.csv").write_text("person_key,month\n00000000042,2026-01-01\n", encoding="utf-8")
            df = consolidate.read_many(Path(d))
        self.assertEqual(df["person_key"].tolist(), ["00000000042", "00123456789"])  # leading zeros survive
        self.assertEqual(df["source_file"].tolist(), ["a.csv", "b.csv"])  # sorted by file name

    def test_ignores_files_that_are_not_csv(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.csv").write_text("x\n1\n", encoding="utf-8")
            (Path(d) / "notes.txt").write_text("not data", encoding="utf-8")
            df = consolidate.read_many(Path(d))
        self.assertEqual(len(df), 1)


class HeadcountTests(unittest.TestCase):
    def test_keeps_the_last_version_of_a_month_and_trims_text(self) -> None:
        with sample_dir() as d:
            write_csv(d / "headcount" / "headcount_2026-01.csv",
                      [hc_row("2026-01-01", "1", "3573322108", company="  Acme A  "), hc_row("2026-01-01", "2", "5")])
            write_csv(d / "headcount" / "headcount_2026-02.csv",
                      [hc_row("2026-02-01", "1", "3573322108"),
                       hc_row("2026-01-01", "1", "3573322108", company="Acme B")])  # corrected version of January
            df = consolidate.build_headcount()
        self.assertEqual(len(df), 3)
        january_1 = df[(df["month"] == "2026-01-01") & (df["employee_id"] == "1")]
        self.assertEqual(january_1["company"].tolist(), ["Acme B"])  # the later file wins
        self.assertTrue(df["company"].str.strip().eq(df["company"]).all())
        self.assertTrue(df["person_key"].str.len().eq(11).all())


class ExitsTests(unittest.TestCase):
    def test_cumulative_repeats_collapse_even_when_the_key_lost_its_zero(self) -> None:
        with sample_dir() as d:
            write_csv(d / "exits" / "exits_2026-01.csv", [exit_row("03573322108", "2026-01-10")])
            write_csv(d / "exits" / "exits_2026-02.csv", [
                exit_row("3573322108", "2026-01-10"),    # same person and date, key written as a number
                exit_row("00000000001", "2026-02-05")])
            df = consolidate.build_exits()
        self.assertEqual(sorted(df["person_key"]), ["00000000001", "03573322108"])
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df["exit_date"]))

    def test_same_person_on_different_dates_is_kept(self) -> None:
        with sample_dir() as d:
            write_csv(d / "exits" / "exits_2026-01.csv",
                      [exit_row("03573322108", "2026-01-10"), exit_row("03573322108", "2026-06-10")])
            df = consolidate.build_exits()
        self.assertEqual(len(df), 2)


class RequisitionsTests(unittest.TestCase):
    def test_days_to_close_and_open_requisitions(self) -> None:
        with sample_dir() as d:
            write_csv(d / "requisitions.csv", [
                {"req_id": "R1", "company": "Acme A", "department": "Ops", "opened_date": "2026-01-01",
                 "closed_date": "2026-01-31", "source": "External"},
                {"req_id": "R2", "company": "Acme A", "department": "Ops", "opened_date": "2026-02-01",
                 "closed_date": "", "source": "External"}])
            df = consolidate.build_requisitions()
        self.assertEqual(df["days_to_close"].iloc[0], 30)
        self.assertTrue(pd.isna(df["days_to_close"].iloc[1]))


class TalentBridgeTests(unittest.TestCase):
    def test_maps_ids_to_keys_once_and_leaves_unmatched_empty(self) -> None:
        headcount = pd.DataFrame({"employee_id": ["1", "1", "2"],  # employee 1 appears in two months
                                  "person_key": ["00000000001", "00000000001", "00000000002"]})
        with sample_dir() as d:
            write_csv(d / "talent_calibration.csv",
                      [{"employee_id": "1", "cycle": "C1"}, {"employee_id": "9", "cycle": "C1"}])
            out = consolidate.build_talent_bridge(headcount)
        self.assertEqual(len(out), 2)  # the repeated months did not duplicate the talent row
        self.assertEqual(out.loc[out["employee_id"] == "1", "person_key"].tolist(), ["00000000001"])
        self.assertTrue(pd.isna(out.loc[out["employee_id"] == "9", "person_key"]).all())


class MainTests(unittest.TestCase):
    def test_writes_the_four_bronze_tables(self) -> None:
        with sample_dir() as d, tempfile.TemporaryDirectory() as out:
            write_csv(d / "headcount" / "headcount_2026-01.csv", [hc_row("2026-01-01", "1", "3573322108")])
            write_csv(d / "exits" / "exits_2026-01.csv", [exit_row("3573322108", "2026-01-20")])
            write_csv(d / "requisitions.csv", [{"req_id": "R1", "company": "Acme A", "department": "Ops",
                                                "opened_date": "2026-01-01", "closed_date": "2026-01-31",
                                                "source": "External"}])
            write_csv(d / "talent_calibration.csv", [{"employee_id": "1", "cycle": "C1"}])
            with mock.patch.object(consolidate, "BRONZE", Path(out) / "bronze"):
                consolidate.main()
            names = sorted(p.name for p in (Path(out) / "bronze").glob("*.parquet"))
        self.assertEqual(names, ["exits.parquet", "headcount.parquet", "requisitions.parquet", "talent.parquet"])


if __name__ == "__main__":
    unittest.main()
