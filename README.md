# People Analytics Catalog

Português: [README.pt-BR.md](README.pt-BR.md)

Data engineering and AI agent patterns for People Analytics, demonstrated with **100% synthetic data** from a fictional company (Acme Retail Group).

> Focus: the **method**. No numbers, names, rules or documents from any employer appear here. See [DISCLAIMER.md](DISCLAIMER.md).

## Projects

| # | Project | What it shows | Status |
|---|---|---|---|
| 01 | [Data lineage of an AI agent](projects/01-ai-agent-data-lineage) | Interactive map of the 8 layers, from source to chat, with Bronze/Gold and k-anonymity | Done |
| 02 | [ETL and consolidation pattern](projects/02-etl-consolidation-pattern) | Runnable Bronze → Gold pipeline: monthly consolidation, dedup, ID → key bridge, small-group suppression | Done |
| 03 | [Staged assistant architecture](projects/03-staged-assistant-architecture) | Answer cheap first (pandas), call an LLM only when needed | Done |

## Run the example

```bash
py synthetic-data/generate.py
py projects/02-etl-consolidation-pattern/src/consolidate.py
py projects/02-etl-consolidation-pattern/src/build_gold.py
py projects/03-staged-assistant-architecture/src/evaluate.py
```

Requires Python 3.10+ with `pandas`, `pyarrow` and `openpyxl`. Outputs go to `out/` (ignored by git).
Live map: https://gustavo-analytics.github.io/people-analytics-catalog/ (or open `projects/01-ai-agent-data-lineage/index.html` in a browser).

## Safety of this repository

- `tools/guard.py` scans the repository for forbidden terms, valid CPF numbers, e-mail addresses, machine paths, embedded images and data files. Run it before every commit, or install the hook (`tools/pre-commit`).
- Synthetic data uses CPF numbers with an **intentionally invalid** check digit, so the guard can tell test data from real data.
- `.parquet`, `.xlsx` and similar files are in `.gitignore`.

## License

[MIT](LICENSE)

## Author

Gustavo, People Analytics. [LinkedIn](https://www.linkedin.com/in/gustavo-13p/)
