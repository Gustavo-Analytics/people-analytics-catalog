# 01 · Data lineage of an AI agent

Português: [README.pt-BR.md](README.pt-BR.md) · Interactive map: [index.html](index.html) ([live](https://gustavo-analytics.github.io/people-analytics-catalog/))

An interactive map (`index.html`) of the path an HR data point takes, from the source system to an agent's answer in a chat. Plain HTML, CSS and JavaScript, no build step. Styles and the map engine live in `assets/`.

The Poppins font loads from Google Fonts. To avoid that third-party request, remove the font `<link>` in the page and it falls back to the system font.

## Problem

An AI agent that answers People Analytics questions needs data about people. The same data brings risk: identifying individuals, wrong numbers from the wrong file, and invented answers when information is missing.

## Solution in one sentence

The agent **only reads a Gold layer, anonymized and aggregated**. The nominal layer (Bronze) exists but stays out of its reach.

```
Sources → ETL → Bronze (nominal) → Aggregation → Gold (anonymized) → Knowledge folder → Agent → Chat
```

## Design decisions

| Decision | Why |
|---|---|
| Bronze/Gold medallion | Separates who calculates (access to nominal data) from who answers (aggregates only). |
| Gold always in `.xlsx` | The platform's knowledge source does not read `.parquet`. |
| k-anonymity at aggregation | A small group is identifiable by exclusion. Below k, the value is suppressed. |
| One master file per view | One card per company and month. Stops the agent from joining support files on its own. |
| A "standardized" file per view | If a version with the right filter exists (for example, core contracts only), the agent is forbidden from using the generic version. |
| Indicator without a source = `n/a` | Estimating or approximating produces a plausible, wrong number. Declaring the absence is more honest. |
| Fixed fallback on the master | If the master is not indexed yet, the instructions say which file to use. The agent does not choose. |

## Lessons learned

1. **Indexing takes time.** Testing right after publishing gives false negatives. Changing the source means remove, publish, wait, re-add and publish again.
2. **Normalize keys on both sides of a join.** A leading zero lost by numeric parsing makes the join fail without an error.
3. **Every block that depends on a master needs a fallback.** Otherwise the agent picks the "closest" file and gets the scale wrong.
4. **Standardize the scale of percentage columns** across files (fraction or ×100, never both).
5. **Very long conversations in a chat channel can degrade answers.** Restarting the conversation fixes it.
6. **Do not publish the total next to a suppressed cut.** Subtraction reveals the hidden cell.

## Agent instruction pattern

See [docs/agent-instructions-pattern.md](docs/agent-instructions-pattern.md).

## Using the map

Open `index.html`. Hover or click a block to highlight everything that feeds it and everything it feeds. The map data is in the `DATA` object at the end of the file and is fictional. A Portuguese version is in [index.pt-BR.html](index.pt-BR.html).
