"""Stand-ins for a real LLM, so the example runs without network or API key.

To plug in a real model, pass any function `llm(prompt) -> str` and
`codegen(question, schema) -> str` to `answer()`. Read the key from an environment variable,
never from a versioned file.
"""
from periods import norm


class StubLLM:
    """Extractive: returns the first lines of the context. Counts how many times it was called."""

    def __init__(self):
        self.calls = 0

    def __call__(self, prompt: str) -> str:
        self.calls += 1
        context = prompt.split("CONTEXTO:")[1].split("PERGUNTA:")[0].strip()
        return "[stub-llm] Com base no contexto: " + " | ".join(context.splitlines()[:3])


class StubCodegen:
    """Fixed rules in place of a code-generating model. Counts the calls."""

    def __init__(self):
        self.calls = 0

    def __call__(self, question: str, schema: dict) -> str:
        self.calls += 1
        nq = norm(question)
        if "turnover" in nq:
            return ("result = turnover.dropna(subset=['turnover_pct']).groupby('company')"
                    "['turnover_pct'].mean().sort_values(ascending=False).round(4)")
        if "headcount" in nq:
            return "result = headcount.groupby('company')['headcount'].mean().sort_values(ascending=False).round(1)"
        if "mulher" in nq:
            ascending = "menor" in nq
            return ("last = headcount[headcount['month'] == headcount['month'].max()]\n"
                    f"result = last.set_index('company')['women_pct'].sort_values(ascending={ascending})")
        raise NotImplementedError("no rule for this question")
