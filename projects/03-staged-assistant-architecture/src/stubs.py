"""Substitutos de um LLM real, para o exemplo rodar sem rede e sem chave de API.

Para ligar um modelo de verdade, passe qualquer função `llm(prompt) -> str` e
`codegen(question, schema) -> str` ao `answer()`. Leia a chave de uma variável de ambiente,
nunca de um arquivo versionado.
"""
from periods import norm


class StubLLM:
    """Extrativo: devolve as primeiras linhas do contexto. Conta quantas vezes foi chamado."""

    def __init__(self):
        self.calls = 0

    def __call__(self, prompt: str) -> str:
        self.calls += 1
        context = prompt.split("CONTEXTO:")[1].split("PERGUNTA:")[0].strip()
        return "[stub-llm] Com base no contexto: " + " | ".join(context.splitlines()[:3])


class StubCodegen:
    """Regras fixas no lugar de um modelo gerador de código. Conta as chamadas."""

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
        raise NotImplementedError("sem regra para esta pergunta")
