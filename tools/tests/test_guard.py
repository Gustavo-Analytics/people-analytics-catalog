"""Tests of the publication guard: what it flags, what it lets through and how it exits.

The sensitive-looking samples are assembled from pieces, so this file does not trip the guard itself.
"""
import contextlib
import io
import sys
import tempfile
import unittest
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import guard  # noqa: E402

VALID_CPF = "529982247" + "25"      # passes the check-digit rule
INVALID_CPF = "529982247" + "26"    # same digits, wrong check digit (what the synthetic CPFs look like)
BS = chr(92)                        # a backslash
CORP_EMAIL = "someone" + "@" + "corp.net"


@contextlib.contextmanager
def repo() -> Iterator[Path]:
    """A temporary folder that stands in for the repository root."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        with mock.patch.object(guard, "ROOT", root), \
                mock.patch.object(guard, "TERMS_FILE", root / "tools" / "guard_terms.local.txt"):
            yield root


def reasons(root: Path, text: str, name: str = "note.md", terms: list[str] | None = None,
            allow: set[str] | None = None) -> list[str]:
    """Writes `text` to a file under `root` and returns the reasons the guard gives for it."""
    path = root / name
    path.write_text(text, encoding="utf-8")
    return [why for _, _, why in guard.scan(path, terms or [], allow or set())]


class CpfTests(unittest.TestCase):
    def test_valid_cpf_passes_the_rule(self) -> None:
        self.assertTrue(guard.cpf_is_valid(VALID_CPF))

    def test_wrong_check_digit_fails(self) -> None:
        self.assertFalse(guard.cpf_is_valid(INVALID_CPF))

    def test_repeated_digits_fail(self) -> None:
        self.assertFalse(guard.cpf_is_valid("1" * 11))


class ScanTests(unittest.TestCase):
    def test_forbidden_term_is_flagged_ignoring_case(self) -> None:
        with repo() as root:
            found = reasons(root, "this mentions SECRET-CO twice\nsecret-co", terms=["secret-co"])
        self.assertEqual(sum("forbidden term" in r for r in found), 2)

    def test_forbidden_term_in_a_file_name_is_flagged(self) -> None:
        with repo() as root:
            found = reasons(root, "harmless", name="secret-co-notes.md", terms=["secret-co"])
        self.assertTrue(any("file name" in r for r in found))

    def test_valid_cpf_is_flagged_in_both_formats_but_a_synthetic_one_is_not(self) -> None:
        formatted = f"{VALID_CPF[:3]}.{VALID_CPF[3:6]}.{VALID_CPF[6:9]}-{VALID_CPF[9:]}"
        with repo() as root:
            self.assertIn("possible valid CPF", reasons(root, f"cpf {VALID_CPF}"))
            self.assertIn("possible valid CPF", reasons(root, f"cpf {formatted}"))
            self.assertEqual(reasons(root, f"cpf {INVALID_CPF}"), [])

    def test_email_is_flagged_unless_example_noreply_or_allowed(self) -> None:
        with repo() as root:
            self.assertIn("e-mail address found", reasons(root, f"contact {CORP_EMAIL}"))
            self.assertEqual(reasons(root, "a@" + "example.org"), [])
            self.assertEqual(reasons(root, "1+user@users." + "noreply.github.com"), [])
            self.assertEqual(reasons(root, f"contact {CORP_EMAIL}", allow={CORP_EMAIL}), [])

    def test_machine_paths_and_cloud_folders_are_flagged(self) -> None:
        drive_path = "C:" + BS + "Users" + BS + "someone"
        with repo() as root:
            self.assertIn("machine/cloud path", reasons(root, drive_path))
            self.assertIn("machine/cloud path", reasons(root, "folder One" + "Drive here"))

    def test_guid_is_flagged(self) -> None:
        guid = "123e4567-e89b-12d3-a456-" + "426614174000"
        with repo() as root:
            self.assertIn("GUID (possible internal ID)", reasons(root, f"id {guid}"))

    def test_embedded_image_is_flagged(self) -> None:
        with repo() as root:
            found = reasons(root, "src=data:image/png;base64," + "A" * 2100, name="page.html")
        self.assertTrue(any("base64" in r for r in found))

    def test_data_extensions_and_large_files_are_flagged(self) -> None:
        with repo() as root:
            (root / "table.parquet").write_bytes(b"PAR1")
            blocked = guard.scan(root / "table.parquet", [], set())
            self.assertTrue(any("blocked extension" in why for _, _, why in blocked))
            with mock.patch.object(guard, "MAX_BYTES", 10):
                found = reasons(root, "x" * 50)
        self.assertTrue(any("large file" in r for r in found))

    def test_a_file_that_is_not_utf8_is_reported(self) -> None:
        with repo() as root:
            (root / "bad.md").write_bytes(b"\xff\xfe\x00bad")
            found = [why for _, _, why in guard.scan(root / "bad.md", [], set())]
        self.assertTrue(any("not UTF-8" in r for r in found))

    def test_clean_text_has_no_findings(self) -> None:
        with repo() as root:
            self.assertEqual(reasons(root, "Nothing to see here.\nJust a sentence."), [])

    def test_the_terms_file_itself_is_never_scanned(self) -> None:
        with repo() as root:
            terms_file = root / "tools" / "guard_terms.local.txt"
            terms_file.parent.mkdir()
            terms_file.write_text("secret-co\n", encoding="utf-8")
            self.assertEqual(guard.scan(terms_file, ["secret-co"], set()), [])


class LoadTermsTests(unittest.TestCase):
    def test_reads_terms_and_allow_list_and_skips_comments(self) -> None:
        with repo() as root:
            (root / "tools").mkdir()
            (root / "tools" / "guard_terms.local.txt").write_text(
                f"# comment\n\nSecret-Co\nallow: {CORP_EMAIL.upper()}\n", encoding="utf-8")
            terms, allow = guard.load_terms()
        self.assertEqual(terms, ["secret-co"])
        self.assertEqual(allow, {CORP_EMAIL})

    def test_missing_file_only_warns(self) -> None:
        with repo(), contextlib.redirect_stdout(io.StringIO()) as out:
            terms, allow = guard.load_terms()
        self.assertEqual((terms, allow), ([], set()))
        self.assertIn("WARNING", out.getvalue())


class CandidateFilesTests(unittest.TestCase):
    def test_walks_the_tree_but_skips_ignored_folders(self) -> None:
        with repo() as root:
            for rel in ("a.md", "sub/b.md", "out/c.md", ".git/d.md", "sub/__pycache__/e.md"):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("x", encoding="utf-8")
            found = sorted(p.relative_to(root).as_posix() for p in guard.candidate_files(False))
        self.assertEqual(found, ["a.md", "sub/b.md"])

    def test_staged_mode_asks_git(self) -> None:
        git_output = mock.Mock(stdout="a.md\nsub/b.md\n")
        with repo() as root, mock.patch.object(guard.subprocess, "run", return_value=git_output):
            found = guard.candidate_files(True)
        self.assertEqual(found, [root / "a.md", root / "sub" / "b.md"])


class MainTests(unittest.TestCase):
    def test_exits_with_code_1_and_lists_the_finding(self) -> None:
        with repo() as root, mock.patch.object(sys, "argv", ["guard.py"]), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            (root / "note.md").write_text(f"cpf {VALID_CPF}", encoding="utf-8")
            with self.assertRaises(SystemExit) as raised:
                guard.main()
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("BLOCKED", out.getvalue())
        self.assertIn("note.md:1", out.getvalue())

    def test_passes_on_a_clean_tree(self) -> None:
        with repo() as root, mock.patch.object(sys, "argv", ["guard.py"]), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            (root / "note.md").write_text("all good", encoding="utf-8")
            guard.main()
        self.assertIn("OK: 1 file(s) checked", out.getvalue())


if __name__ == "__main__":
    unittest.main()
