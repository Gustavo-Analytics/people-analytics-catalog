"""Tests of the golden rules. They use small in-memory tables, independent of the generated Gold.

Usage: py -m unittest discover -s projects/03-staged-assistant-architecture/tests
"""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assistant import answer  # noqa: E402
from periods import parse_period  # noqa: E402
from sandbox import SandboxError, run_sandboxed  # noqa: E402

MONTHS = ["2026-08-01", "2026-09-01", "2026-10-01"]


def make_tables():
    hc = pd.DataFrame({"month": MONTHS * 2, "company": ["Acme A"] * 3 + ["Acme B"] * 3,
                       "headcount": [100, 102, 104, 20, 21, 22], "women": [40, 41, 42, 9, 9, 10],
                       "women_pct": [0.40, 0.4020, 0.4038, 0.45, 0.4286, 0.4545], "suppressed": [False] * 6})
    to = pd.DataFrame({"month": MONTHS * 2, "company": ["Acme A"] * 3 + ["Acme B"] * 3,
                       "headcount": [100, 102, 104, 20, 21, 22],
                       "turnover_pct": [0.03, 0.02, 0.04, None, None, None],
                       "suppressed": [False, False, False, True, True, True]})
    tth = pd.DataFrame({"month": MONTHS, "company": ["Acme A"] * 3, "avg_days": [40.0, 42.0, 38.0],
                        "suppressed": [False] * 3})
    regret = pd.DataFrame({"company": ["Acme A", "Acme B"], "regrettable_pct": [0.1, None],
                           "suppressed": [False, True]})
    return {"headcount": hc, "turnover": to, "tth": tth, "regret": regret, "kpi": pd.DataFrame()}


class Counting:
    def __init__(self):
        self.calls = 0

    def __call__(self, *args):
        self.calls += 1
        return "[llm]"


class PeriodTests(unittest.TestCase):
    def test_named_month_without_year_uses_latest_match(self):
        self.assertEqual(parse_period("em setembro", MONTHS), ("2026-09-01", "ok"))

    def test_abbreviation_and_two_digit_year(self):
        self.assertEqual(parse_period("out/26", MONTHS), ("2026-10-01", "ok"))

    def test_previous_month(self):
        self.assertEqual(parse_period("no mês passado", MONTHS), ("2026-09-01", "ok"))

    def test_missing_month_is_out_of_range(self):
        self.assertEqual(parse_period("em janeiro de 2024", MONTHS)[1], "out_of_range")

    def test_no_period(self):
        self.assertEqual(parse_period("qual o headcount?", MONTHS), (None, "none"))


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.t, self.llm, self.code = make_tables(), Counting(), Counting()

    def test_lookup_needs_no_llm(self):
        a = answer("Qual o headcount da Acme A?", self.t, llm=self.llm, codegen=self.code)
        self.assertEqual(a.stage, 0)
        self.assertIn("104", a.text)
        self.assertEqual(self.llm.calls, 0)

    def test_unavailable_metric_never_reaches_llm(self):
        a = answer("Explique o engajamento", self.t, llm=self.llm, codegen=self.code)
        self.assertEqual(a.kind, "unavailable")
        self.assertEqual(self.llm.calls, 0)

    def test_out_of_range_never_reaches_llm(self):
        a = answer("Explique o turnover em janeiro de 2020", self.t, llm=self.llm, codegen=self.code)
        self.assertEqual(a.stage, 0.5)
        self.assertEqual(self.llm.calls, 0)

    def test_suppressed_value_is_not_reconstructed(self):
        a = answer("Turnover da Acme B", self.t)
        self.assertIn("não divulgado", a.text)

    def test_out_of_scope_goes_to_fallback(self):
        a = answer("Qual a capital da França?", self.t, llm=self.llm)
        self.assertEqual(a.stage, 3)
        self.assertEqual(self.llm.calls, 0)

    def test_without_llm_explain_falls_back(self):
        self.assertEqual(answer("Explique o turnover", self.t).stage, 3)


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.t = make_tables()

    def test_runs_safe_analysis(self):
        r = run_sandboxed("result = headcount['headcount'].sum()", self.t)
        self.assertEqual(int(r), 369)

    def test_blocks_import(self):
        with self.assertRaises(SandboxError):
            run_sandboxed("import os\nresult = 1", self.t)

    def test_blocks_file_write(self):
        with self.assertRaises(SandboxError):
            run_sandboxed("headcount.to_csv('x.csv')\nresult = 1", self.t)

    def test_blocks_private_attribute(self):
        with self.assertRaises(SandboxError):
            run_sandboxed("result = headcount.__class__", self.t)

    def test_requires_result(self):
        with self.assertRaises(SandboxError):
            run_sandboxed("x = 1", self.t)


if __name__ == "__main__":
    unittest.main()
