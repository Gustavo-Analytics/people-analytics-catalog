"""Runs every test suite of the repository in one process (used by CI and for coverage).

Usage: py tools/run_tests.py
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUITES = [
    ROOT / "projects" / "02-etl-consolidation-pattern" / "tests",
    ROOT / "projects" / "03-staged-assistant-architecture" / "tests",
    ROOT / "synthetic-data" / "tests",
    ROOT / "tools" / "tests",
]


def main() -> int:
    """Discovers and runs all suites; returns 0 if every test passes, 1 otherwise."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for directory in SUITES:
        suite.addTests(loader.discover(str(directory), top_level_dir=str(directory)))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
