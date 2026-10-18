# eval/

Evaluation set and scorer for AskData: 52 questions over the Pagila and retail_ops demo datasets (answerable, ambiguous, unanswerable, schema lookups), split into **dev** (20, the code was tuned on these) and **held-out** (32).

| File | What |
|---|---|
| `questions.json` | Questions, gold SQL (one or more accepted readings), matching rules |
| `expected.json` | Saved results of every gold query (UTC, read-only) |
| `score.py` | Runs questions against the backend and scores them; `--rescore`, `--summarize` |
| `test_score.py` | Tests for the matcher and outcomes (`python eval/test_score.py`) |
| `build_expected.py` | Regenerates `expected.json` from the database |
| `results/` | Run outputs (`<time>_<label>_<dataset>.jsonl` + `.summary.json`) |

Full description, metrics and response contract: [`EVAL.md`](EVAL.md).
