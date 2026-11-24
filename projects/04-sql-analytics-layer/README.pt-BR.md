# 04 · Camada SQL de análise

English: [README.md](README.md)

O mesmo Gold, consultado com **SQL** em vez de pandas. O [DuckDB](https://duckdb.org) roda dentro do Python (sem servidor, sem rede, sem credenciais), carrega as planilhas Gold do [projeto 02](../02-etl-consolidation-pattern) e as expõe por meio de views governadas.

```
out/gold/*.xlsx  ──►  gold.*        cópias das tabelas Gold (célula suprimida vira NULL)
                         │  sql/views.sql
                         ▼
                      analytics.*   views governadas: o único schema que um consumidor consulta
                         │  sql/queries/*.sql
                         ▼
                      consultas nomeadas e versionadas (ranking, tendência, média móvel, auditoria de privacidade)
```

## Como rodar

Exige o Gold gerado pelo projeto 02:

```bash
py synthetic-data/generate.py
py projects/02-etl-consolidation-pattern/src/consolidate.py
py projects/02-etl-consolidation-pattern/src/build_gold.py
py projects/04-sql-analytics-layer/src/warehouse.py                  # lista as consultas guardadas
py projects/04-sql-analytics-layer/src/warehouse.py turnover_ranking
py projects/04-sql-analytics-layer/src/warehouse.py privacy_audit    # código de saída 1 se alguma célula quebrar o k-anonimato
```

## Consultas guardadas

| Consulta | O que mostra | Técnica de SQL |
|---|---|---|
| `turnover_ranking` | Último turnover mensal publicado por empresa, em ranking | CTE + `QUALIFY` + `rank()` |
| `headcount_trend` | Últimos 3 meses de headcount e variação mês a mês | `LAG()`, `QUALIFY` |
| `turnover_rolling` | Turnover móvel de 3 meses, só onde ao menos 2 meses foram publicados | janela `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` |
| `privacy_audit` | Toda célula publicada que quebra a regra de k-anonimato (deve vir vazia) | `UNION ALL` de regras, uma por tabela Gold |

## Decisões de projeto

1. **Quem consome consulta `analytics.*`, nunca `gold.*`.** As views são o contrato. Uma tabela pode mudar por baixo sem quebrar um painel ou um agente.
2. **Célula suprimida é NULL, e agregação ignora NULL.** Um valor oculto nunca é tratado como zero nem reconstruído. A view móvel também devolve `months_with_data`, então uma média com poucos meses parece fraca.
3. **Empresa sem nada publicado não aparece no ranking.** Não há o que ordenar, e a consulta não inventa valor.
4. **A privacidade é auditada em SQL.** `analytics.privacy_violations` reconfere os limites do projeto 02 (k = 3 e k = 5) nas tabelas publicadas e também aponta linha marcada como suprimida que ainda carrega valor. É uma segunda linha de defesa: a primeira é o `build_gold.py`.
5. **Só consultas guardadas rodam pela linha de comando.** O nome é procurado numa lista fixa, então não dá para passar caminho de arquivo nem SQL livre.

## Um erro que os testes pegaram

Minha primeira versão do ranking colocava `rank()` e `QUALIFY row_number() = 1` no mesmo `SELECT`. A janela roda *antes* do `QUALIFY`, então ela ordenava todos os meses de todas as empresas e as posições saíam 1, 3, 5, 12. A correção é escolher o último mês de cada empresa numa CTE e só depois ordenar. Um teste agora confere que as posições não têm buracos.

## Limitações conhecidas

- **As tabelas são recarregadas das planilhas a cada execução.** Serve para algumas centenas de linhas. Em volume real, o Gold seria gravado direto em Parquet ou em um banco.
- **A auditoria repete à mão os limites do projeto 02.** Se `K_DEFAULT` mudar lá, o `views.sql` precisa mudar também. Uma configuração compartilhada tiraria essa duplicação.
- **Ela audita as contagens que o pipeline promete proteger** (headcount, saídas, vagas fechadas, saídas voluntárias). Colunas derivadas, como o número de mulheres em um recorte, não são auditadas.
- **Ainda não está ligada ao assistente do projeto 03.** O assistente continua lendo as planilhas com pandas.

## Estrutura

```
src/warehouse.py              carrega o Gold no DuckDB, cria as views, roda as consultas guardadas
sql/views.sql                 as views governadas e a auditoria de privacidade
sql/queries/*.sql             consultas guardadas
tests/test_warehouse.py       26 testes: tratamento de NULL, views, consultas, regras da auditoria, linha de comando
```
