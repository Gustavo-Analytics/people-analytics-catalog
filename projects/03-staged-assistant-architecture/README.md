# 03 · Arquitetura de assistente em estágios (planejado)

Ideia: responder cada pergunta no estágio **mais barato que resolva**, e só subir para o LLM quando necessário.

| Estágio | O que faz | Custo |
|---|---|---|
| 0 | Pandas puro: métricas diretas ("qual o headcount?") | Zero de LLM |
| 0.5 | Parser de período: interpreta mês, ano fiscal ou trimestre antes de qualquer chamada | Zero de LLM |
| 1 | Monta o contexto relevante e envia ao LLM | Baixo |
| 2 | LLM gera código de análise sob demanda, executado em ambiente controlado | Médio |
| 3 | Fallback: resposta controlada quando nenhum estágio resolveu | Zero |

## A fazer

- Exemplo executável sobre o Gold sintético do projeto 02.
- Medir quantas perguntas cada estágio resolve num conjunto de teste.
- Autenticação e leitura de dados privados (padrão genérico, sem credenciais no repositório).
