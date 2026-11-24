"""Tests of the sandbox that runs analysis code written by a model."""
import ast
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sandbox import SandboxError, run_sandboxed, validate  # noqa: E402


class SandboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tables = {"df": pd.DataFrame({"n": [1, 2, 3]})}

    def test_returns_the_result_variable(self) -> None:
        self.assertEqual(int(run_sandboxed("result = df['n'].sum()", self.tables)), 6)

    def test_validate_returns_the_parsed_module(self) -> None:
        self.assertIsInstance(validate("result = 1"), ast.Module)

    def test_rejects_invalid_syntax(self) -> None:
        with self.assertRaises(SandboxError) as raised:
            run_sandboxed("result = (", self.tables)
        self.assertIn("invalid code", str(raised.exception))

    def test_wraps_runtime_errors(self) -> None:
        with self.assertRaises(SandboxError) as raised:
            run_sandboxed("result = 1 / 0", self.tables)
        self.assertIn("ZeroDivisionError", str(raised.exception))

    def test_blocks_dangerous_names(self) -> None:
        for name in ("eval", "open", "__import__", "getattr"):
            with self.subTest(name=name), self.assertRaises(SandboxError) as raised:
                run_sandboxed(f"result = {name}('x')", self.tables)
            self.assertIn("blocked name", str(raised.exception))

    def test_blocks_global_and_nonlocal_statements(self) -> None:
        with self.assertRaises(SandboxError) as raised:
            run_sandboxed("global x\nresult = 1", self.tables)
        self.assertIn("global scope", str(raised.exception))

    def test_allows_display_conversions_but_not_writes(self) -> None:
        self.assertIn("n", run_sandboxed("result = df.to_string()", self.tables))
        for code in ("result = df.to_csv('out.csv')", "result = df.to_pickle('x')"):
            with self.subTest(code=code), self.assertRaises(SandboxError) as raised:
                run_sandboxed(code, self.tables)
            self.assertIn("blocked attribute", str(raised.exception))

    def test_only_a_few_builtins_exist_inside(self) -> None:
        self.assertEqual(run_sandboxed("result = len(df)", self.tables), 3)
        with self.assertRaises(SandboxError) as raised:
            run_sandboxed("result = print", self.tables)  # print is not exposed
        self.assertIn("NameError", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
