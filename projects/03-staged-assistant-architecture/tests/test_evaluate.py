"""Tests of the evaluation runner and of the stand-ins for a real model."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import evaluate  # noqa: E402
from stubs import StubCodegen, StubLLM  # noqa: E402
from test_assistant import make_tables  # noqa: E402


def run_with(csv_text: str, verbose: bool = False) -> tuple[int, str]:
    """Runs the evaluation on a tiny question set and in-memory tables; returns (exit code, printed text)."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "questions.csv"
        path.write_text(csv_text, encoding="utf-8")
        out = io.StringIO()
        with mock.patch.object(evaluate, "QUESTIONS", path), \
                mock.patch.object(evaluate, "load_tables", make_tables), contextlib.redirect_stdout(out):
            code = evaluate.main(verbose)
    return code, out.getvalue()


class EvaluateTests(unittest.TestCase):
    def test_returns_zero_when_every_expectation_is_met(self) -> None:
        code, printed = run_with(
            "question,expected_stage,must_contain\n"
            "Qual o headcount da Acme A?,0,104\n"
            "Explique o engajamento,0,não disponível\n"
            "Qual a capital da França?,3,Não encontrei\n")
        self.assertEqual(code, 0)
        self.assertIn("3 questions | LLM calls: 0", printed)
        self.assertIn("without LLM: 3 of 3", printed)

    def test_returns_one_and_prints_the_answer_when_an_expectation_fails(self) -> None:
        code, printed = run_with("question,expected_stage,must_contain\nQual o headcount da Acme A?,2,104\n")
        self.assertEqual(code, 1)
        self.assertIn("[FAILED]", printed)

    def test_counts_llm_and_code_generation_calls(self) -> None:
        code, printed = run_with(
            "question,expected_stage,must_contain\n"
            "Explique o turnover da Acme A,1,[stub-llm]\n"
            "Ranking de turnover por empresa,2,Acme\n", verbose=True)
        self.assertEqual(code, 0)
        self.assertIn("LLM calls: 1 | code generation: 1", printed)
        self.assertIn("code: result =", printed)  # verbose mode shows the code that ran


class StubTests(unittest.TestCase):
    def test_stub_llm_answers_from_the_context_and_counts_calls(self) -> None:
        llm = StubLLM()
        text = llm("CONTEXTO:\nlinha 1\nlinha 2\nlinha 3\nlinha 4\nPERGUNTA:\n?")
        self.assertEqual(text, "[stub-llm] Com base no contexto: linha 1 | linha 2 | linha 3")
        self.assertEqual(llm.calls, 1)

    def test_stub_codegen_knows_a_few_questions_and_refuses_the_rest(self) -> None:
        codegen = StubCodegen()
        self.assertIn("turnover_pct", codegen("ranking de turnover", {}))
        self.assertIn("ascending=True", codegen("menor percentual de mulheres", {}))
        self.assertIn("ascending=False", codegen("maior percentual de mulheres", {}))
        with self.assertRaises(NotImplementedError):
            codegen("qual a capital da França?", {})
        self.assertEqual(codegen.calls, 4)


if __name__ == "__main__":
    unittest.main()
