# 02 · Padrão de ETL e consolidação

English: [README.md](README.md)

Pipeline executável, sobre dados sintéticos, que leva arquivos mensais soltos até planilhas Gold anonimizadas.

```
synthetic-data/sample/*.csv
        │  src/consolidate.py
        ▼
out/bronze/*.parquet     (nominal, uso interno)
        │  src/build_gold.py
        ▼
out/gold/*.xlsx          (agregado, sem coluna de pessoa)
```

## Como rodar

```bash
py synthetic-data/generate.py
py projects/02-etl-consolidation-pattern/src/consolidate.py
py projects/02-etl-consolidation-pattern/src/build_gold.py
```

Saída esperada do Bronze (semente fixa; as mensagens do script estão em inglês): `headcount: 4890 -> 4890 rows (0 duplicates removed)`, `exits: 125 -> 106 rows (19 duplicates removed)`, `talent: 36 rows, 0 without a match in headcount`.

## O que cada etapa resolve

### consolidate.py (Bronze)
| Problema real | Tratamento |
|---|---|
| Um arquivo por mês | `read_many` lê a pasta inteira e registra o `source_file` de origem |
| CPF perde o zero à esquerda quando lido como número | Ler tudo como texto (`dtype=str`) e normalizar com `zfill(11)` **dos dois lados** do join |
| Relatório cumulativo repete desligamentos | `drop_duplicates` pela chave de negócio (pessoa + data) e log de quantas linhas saíram |
| Lista de talentos só traz o ID | Ponte ID → chave pela tabela de headcount, com contagem de IDs sem correspondência |

### build_gold.py (Gold)
| Regra | Implementação |
|---|---|
| k-anonimato | `suppress()` esvazia a célula abaixo de k e liga a flag `suppressed` |
| k diferente por nível de detalhe | `K_DEFAULT = 3` (empresa), `K_DETAILED = 5` (empresa x departamento) |
| Visão padronizada | Gênero só com vínculos principais (CLT e PJ) em arquivo próprio |
| Indicador sem fonte | `n/a` no card mestre, nunca estimado |
| Reconciliação | `assert`: headcount do card = Bronze; nenhuma coluna de pessoa no Gold |

## Testes

```bash
py -m unittest discover -s projects/02-etl-consolidation-pattern/tests
```

- **Bronze** (`test_consolidate.py`): a chave mantém ou recupera o zero à esquerda, a formatação é removida, a chave gravada como número e a preenchida viram a mesma chave, relatórios cumulativos repetidos colapsam, a versão mais recente de um mês vence, e a ponte ID → chave não duplica linhas e deixa vazios os IDs sem correspondência.
- **Gold** (`test_build_gold.py`): contagens abaixo de k são esvaziadas e sinalizadas (um teste baseado em propriedade confere isso para quaisquer contagens e qualquer k), a visão padronizada de gênero exclui estagiários e aprendizes, o corte fino por departamento usa o K maior, turnover e time to hire são calculados e suprimidos como documentado, indicadores sem fonte saem como `n/a`, nenhuma coluna de pessoa chega ao Gold, e o `main()` para se uma chegar.

Os testes usam tabelas pequenas em memória e só escrevem em pastas temporárias.

## Limitações conhecidas

- **Supressão complementar.** Suprimir uma célula não basta se o total do grupo é publicado: a subtração a revela. Aqui o corte fino não publica total.
- **Turnover de 12 meses** exige série maior que a deste exemplo (12 meses de dado). O exemplo usa turnover mensal.
- A geração é manual. O próximo passo natural é agendar a execução e registrar a reconciliação.

## Estrutura

```
src/consolidate.py   Bronze
src/build_gold.py    Gold + verificações
tests/               testes do Bronze e do Gold
out/                 gerado, ignorado pelo git
```
