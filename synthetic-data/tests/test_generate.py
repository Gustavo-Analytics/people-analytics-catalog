"""Tests of the synthetic data generator: reproducibility, invalid CPFs and the data-window rule."""
import contextlib
import csv
import io
import random
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "synthetic-data"))
sys.path.insert(0, str(ROOT / "tools"))

import generate  # noqa: E402
import guard  # noqa: E402


def run_into(folder: Path) -> None:
    """Runs the generator writing into `folder`, silently."""
    with mock.patch.object(generate, "OUT", folder), contextlib.redirect_stdout(io.StringIO()):
        generate.main()


def read_rows(path: Path) -> list[dict[str, str]]:
    """Reads a CSV file as a list of dictionaries."""
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class GeneratedFilesTests(unittest.TestCase):
    _tmp: tempfile.TemporaryDirectory[str]
    folder: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls._tmp.name)
        run_into(cls.folder)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_same_seed_gives_byte_identical_files(self) -> None:
        with tempfile.TemporaryDirectory() as second:
            run_into(Path(second))
            first_files = sorted(p.relative_to(self.folder) for p in self.folder.rglob("*") if p.is_file())
            second_files = sorted(p.relative_to(second) for p in Path(second).rglob("*") if p.is_file())
            self.assertEqual(first_files, second_files)
            for rel in first_files:
                self.assertEqual((self.folder / rel).read_bytes(), (Path(second) / rel).read_bytes(), rel)

    def test_one_file_per_month_for_headcount_and_exits(self) -> None:
        self.assertEqual(len(list((self.folder / "headcount").glob("*.csv"))), generate.N_MONTHS)
        self.assertEqual(len(list((self.folder / "exits").glob("*.csv"))), generate.N_MONTHS)

    def test_requisitions_never_close_after_the_data_window(self) -> None:
        window_end = generate.month_start(generate.N_MONTHS) - timedelta(days=1)
        closed = [date.fromisoformat(r["closed_date"]) for r in read_rows(self.folder / "requisitions.csv")
                  if r["closed_date"]]
        self.assertTrue(closed)
        self.assertLessEqual(max(closed), window_end)

    def test_exit_reports_repeat_earlier_terminations(self) -> None:
        seen: dict[tuple[str, str], int] = {}
        for path in sorted((self.folder / "exits").glob("*.csv")):
            for r in read_rows(path):
                key = (r["person_key"].zfill(11), r["exit_date"])
                seen[key] = seen.get(key, 0) + 1
        self.assertTrue(any(n > 1 for n in seen.values()), "the cumulative duplicates are the point of the data")

    def test_some_keys_lost_their_leading_zero(self) -> None:
        keys = [r["person_key"] for p in (self.folder / "exits").glob("*.csv") for r in read_rows(p)]
        self.assertTrue(any(len(k) < 11 for k in keys), "a key stored as a number is part of the scenario")


class FakeCpfTests(unittest.TestCase):
    def test_generated_cpfs_are_never_valid_unique_and_eleven_digits(self) -> None:
        used: set[str] = set()
        cpfs = [generate.fake_cpf(random.Random(i), used) for i in range(500)]
        self.assertEqual(len(set(cpfs)), 500)
        for cpf in cpfs:
            self.assertEqual(len(cpf), 11)
            self.assertTrue(cpf.isdigit())
            self.assertFalse(guard.cpf_is_valid(cpf), "a synthetic CPF must never pass the check-digit rule")

    def test_many_cpfs_start_with_zero(self) -> None:
        used: set[str] = set()
        rng = random.Random(7)
        cpfs = [generate.fake_cpf(rng, used) for _ in range(500)]
        self.assertGreater(sum(c.startswith("0") for c in cpfs), 100)  # the leading-zero gotcha needs these


class HelperTests(unittest.TestCase):
    def test_month_start_covers_the_series(self) -> None:
        self.assertEqual(generate.month_start(0), date(2025, 11, 1))
        self.assertEqual(generate.month_start(2), date(2026, 1, 1))  # crosses the year
        self.assertEqual(generate.month_start(11), date(2026, 10, 1))
        self.assertEqual(generate.month_start(12), date(2026, 11, 1))

    def test_pick_follows_the_cumulative_weights(self) -> None:
        class Fixed(random.Random):
            def __init__(self, value: float) -> None:
                super().__init__()
                self.value = value

            def random(self) -> float:
                return self.value

        pairs = [("a", 0.5), ("b", 0.5)]
        self.assertEqual(generate.pick(Fixed(0.2), pairs), "a")
        self.assertEqual(generate.pick(Fixed(0.7), pairs), "b")
        self.assertEqual(generate.pick(Fixed(0.9999), [("a", 0.1), ("b", 0.1)]), "b")  # falls back to the last value


if __name__ == "__main__":
    unittest.main()
