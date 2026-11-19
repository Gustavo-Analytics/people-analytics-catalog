# 02 · ETL and consolidation pattern

Português: [README.pt-BR.md](README.pt-BR.md)

A runnable pipeline, on synthetic data, that takes loose monthly files to anonymized Gold spreadsheets.

```
synthetic-data/sample/*.csv
        │  src/consolidate.py
        ▼
out/bronze/*.parquet     (nominal, internal use)
        │  src/build_gold.py
        ▼
out/gold/*.xlsx          (aggregated, no person column)
```

## How to run

```bash
py synthetic-data/generate.py
py projects/02-etl-consolidation-pattern/src/consolidate.py
py projects/02-etl-consolidation-pattern/src/build_gold.py
```

Expected Bronze output (fixed seed): `headcount: 4890 -> 4890 rows`, `exits: 125 -> 106 rows (19 duplicates removed)`, `talent: 36 rows, 0 without a match in headcount`.

## What each step solves

### consolidate.py (Bronze)
| Real-world problem | Treatment |
|---|---|
| One file per month | `read_many` reads the whole folder and records the origin `source_file` |
| CPF loses its leading zero when read as a number | Read everything as text (`dtype=str`) and normalize with `zfill(11)` on **both sides** of the join |
| Cumulative report repeats terminations | `drop_duplicates` on the business key (person + date) and a log of how many rows were removed |
| Talent list only has the employee ID | ID → person key bridge through the headcount table, with a count of IDs without a match |

### build_gold.py (Gold)
| Rule | Implementation |
|---|---|
| k-anonymity | `suppress()` empties the cell below k and sets the `suppressed` flag |
| Different k per level of detail | `K_DEFAULT = 3` (company), `K_DETAILED = 5` (company x department) |
| Standardized view | Gender only for core contracts (CLT and PJ) in its own file |
| Indicator without a source | `n/a` in the master card, never estimated |
| Reconciliation | `assert`: card headcount = Bronze; no person column in Gold |

## Known limitations

- **Complementary suppression.** Suppressing a cell is not enough if the group total is published: subtraction reveals it. Here the fine cut publishes no total.
- **12-month turnover** needs a longer series than this example (12 months of data). The example uses monthly turnover.
- Generation is manual. The natural next step is to schedule the run and record the reconciliation.

## Structure

```
src/consolidate.py   Bronze
src/build_gold.py    Gold + checks
out/                 generated, ignored by git
```
