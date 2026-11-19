# 03 · Arquitetura de assistente em estágios

English: [README.md](README.md)

Assistente de People Analytics que responde cada pergunta no estágio **mais barato que resolva** e só chama um LLM quando precisa. Roda **sem rede e sem chave de API**: o LLM é uma função plugável e o exemplo usa substitutos (`stubs.py`).

Ele lê o Gold sintético do [projeto 02](../02-etl-consolidation-pattern), que é a única camada que um agente deveria ver.

## Os estágios

| Estágio | O que faz | Chama LLM? | Exemplo |
|---|---|---|---|
| 0 | Lookup direto em pandas: métrica + empresa + mês | Não | "Qual o headcount da Acme Pay em março?" |
| 0.5 | Parser de período. Mês fora da série é respondido na hora | Não | "Headcount em janeiro de 2024" |
| 1 | Contexto filtrado e limitado em tamanho, enviado ao LLM | Sim | "Explique a variação do turnover" |
| 2 | LLM gera código de análise; o código é validado e executado em sandbox | Sim | "Ranking de turnover por empresa" |
| 3 | Fallback controlado | Não | "Qual a capital da França?" |

```
pergunta ─► métrica sem fonte? ─► responde "não disponível"        (nunca sobe)
         ─► período fora da série? ─► responde "fora da série"     (nunca sobe)
         ─► lookup ─► estágio 0
         ─► ranking/média ─► estágio 2 ─► (falhou?) estágio 1
         ─► explique/resuma ─► estágio 1
         ─► o resto ─► estágio 3
```

## Como rodar

Requer o Gold gerado pelo projeto 02:

```bash
py synthetic-data/generate.py
py projects/02-etl-consolidation-pattern/src/consolidate.py
py projects/02-etl-consolidation-pattern/src/build_gold.py
py projects/03-staged-assistant-architecture/src/evaluate.py -v
py -m unittest discover -s projects/03-staged-assistant-architecture/tests
```

## Resultado do conjunto de avaliação

18 perguntas em [eval_questions.csv](eval_questions.csv), com o estágio e um trecho de texto esperados.

| Estágio | Perguntas |
|---|---|
| 0 (lookup) | 11 |
| 0.5 (período) | 1 |
| 1 (LLM com contexto) | 2 |
| 2 (código gerado) | 3 |
| 3 (fallback) | 1 |

13 de 18 foram resolvidas **sem nenhuma chamada de LLM**. Os 16 testes unitários e as 18 perguntas passam.

**Como ler esse número:** as perguntas foram escritas junto com o roteador e o LLM é um substituto. A avaliação prova que o **roteamento** se comporta como projetado, não que um modelo real responda bem. Com um modelo real, a distribuição dependeria das perguntas de quem usa.

## Regras de ouro

1. **Indicador sem fonte nunca sobe de estágio.** Um LLM preencheria a lacuna com algo plausível. A resposta é "não disponível nas fontes atuais".
2. **Mês fora da série nunca sobe de estágio.** É resolvido pelo parser, sem custo.
3. **Valor suprimido por k-anonimato não é reconstruído.** A resposta é "não divulgado por tamanho de grupo". O teste confere que o contador de chamadas de LLM fica em zero nesses casos.
4. **O LLM só vê contexto filtrado.** Empresa e últimos 6 meses da tabela relevante, truncado a 1.500 caracteres, nunca o Gold inteiro.
5. **O código gerado é auditável.** A resposta do estágio 2 guarda o código executado.
6. **Nenhuma credencial no código.** O LLM é `llm(prompt) -> str`. Em uso real, leia a chave de uma variável de ambiente.

## Ligando um modelo real

```python
import os
from assistant import answer, load_tables

def llm(prompt: str) -> str:
    key = os.environ["LLM_API_KEY"]  # nunca versionar
    ...                              # chame o provedor que você usa e devolva o texto

print(answer("Explique o turnover da Acme Retail", load_tables(), llm=llm).text)
```

O mesmo vale para `codegen(question, schema) -> str`, que deve devolver código que atribui a variável `result`.

## Limitações conhecidas

- **O roteamento é por palavra-chave e expressão regular.** É barato e previsível, mas frágil com frases fora do padrão. Um classificador pequeno, ou um LLM só para rotear, seria o próximo passo.
- **O sandbox não é uma fronteira de segurança.** Bloqueia import, atributos privados, escrita em arquivo e funções perigosas, mas não limita tempo nem memória. Em produção, execute o código gerado em processo ou contêiner isolado.
- **Análises geradas podem descartar meses suprimidos em silêncio.** O ranking de turnover do exemplo é a média dos meses não suprimidos. Isso é uma escolha metodológica que a resposta não explicita.
- **O parser de período entende mês e ano.** Trimestre e ano fiscal não estão implementados.
- **"Headcount" aqui é só vínculos principais (CLT e PJ)**, seguindo o arquivo padronizado do projeto 02.

## O que o assistente revelou durante a construção

Ao responder "time to hire", ele devolveu `dez/2026`, depois do fim da série. O problema não era do assistente: o gerador de dados sintéticos deixava vagas fecharem no futuro. Um assistente que declara o mês que usou expõe defeito de dado. Corrigi o gerador e o assistente passou a usar o último mês da **série inteira** como padrão, não o último de cada tabela.

## Estrutura

```
src/periods.py     estágio 0.5: parser de período
src/sandbox.py     estágio 2: validação e execução do código gerado
src/assistant.py   roteador e estágios 0, 1, 2 e 3
src/stubs.py       LLM e gerador de código de mentira, para rodar offline
src/evaluate.py    mede estágio por pergunta e chamadas de LLM
tests/             16 testes das regras de ouro, com tabelas em memória
eval_questions.csv conjunto de avaliação
```
