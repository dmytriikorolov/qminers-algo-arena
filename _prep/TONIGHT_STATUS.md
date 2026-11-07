# Tonight status — verified preparation baseline

Generated 2026-11-06T22:13:11.102725+00:00 (Prague UTC+1). Current code checkpoint: `7cec076f1f8ce33042d80877151d353ad9e7895d`.
Experiment source checkpoint: `6466371`; the later code change only moves a PDF axis label. Original kit preserved in `8df55fa`. All commits are local.

**PASS: 176 tests** (6 original starter + 170 toolkit), no failures or skips in the project venv. The standard-library-only check ran 165 tests, OK with 5 optional skips. No official contest evaluation has run.

## Implemented and changed areas

| Files/area | Working behavior |
|---|---|
| `src/arena/trading.py`, `market_data.py` | Eight mock strategies, Decimal ledger, lifecycle/risk invariants; explicit snapshot/bar/trade CSV features and actual-level top-k depth |
| `src/arena/ml.py` | Mean/ridge and constant/logistic; chronological train/validation/test, train-only preprocessing, row-horizon gap and group-overlap guards |
| `src/arena/games.py`, `algorithms.py` | Six solved example games, knapsack DP/oracle, approximate and optional LP zero-sum solvers; graph/search primitives and small independent oracles |
| `common.py`, `data.py`, `experiments.py`, `cli.py` | Offline inspection, explicit configs, hashes, actual data fingerprints, immutable run IDs, paired named comparisons, stale-validation checks |
| `reporting.py`, `game_reporting.py` | Saved-result HTML/Markdown/PDF; charts and six one-page game answers |
| `preflight.py`, `packaging.py` | Static compile/function/import checks; non-overwriting one-file copy plus provenance manifest; no execution or submission |
| `tests/`, `configs/`, `scenarios/`, `pyproject.toml`, `requirements-local.lock` | Deterministic regression/oracle tests, runnable configurations/examples, isolated optional ARM dependencies |
| `docs/`, `.agents/skills/`, `.github/workflows/tests.yml`, both READMEs | Source/rule review, task classifier, adaptation rehearsal, ten validated command-backed skill outlines, CI configuration (remote CI not run) |
| `experiments/`, `reports/`, `memory/`, `submissions/` | Actual local evidence and readable continuation state; rehearsal artifact explicitly not contest-ready |

## Observed synthetic results

All rows below use seed 7. They test the implementation on stated examples, not competitive edge. The market winner was selected on that path, so its score is not an untouched test result.

| Config | Run ID | Observed result | PDF pages |
|---|---|---|---:|
| market | [20261106T221002-7b7a75883e](experiments/20261106T221002-7b7a75883e/result.json) | 8 strategies; path-selected fixed PnL 29.28 | [2](reports/20261106T221002-7b7a75883e/report.pdf) |
| ml | [20261106T221002-c689560b39](experiments/20261106T221002-c689560b39/result.json) | Test MSE mean 5.510663 vs ridge 0.207773 | [2](reports/20261106T221002-c689560b39/report.pdf) |
| ml_classification | [20261106T221002-40ff7ef576](experiments/20261106T221002-40ff7ef576/result.json) | Test log loss constant 0.702702 vs logistic 0.442000 | [2](reports/20261106T221002-40ff7ef576/report.pdf) |
| games | [20261106T221003-b19503a8c2](experiments/20261106T221003-b19503a8c2/result.json) | Knapsack 19 = oracle; zero-sum best-response gap 0.013997201 | [7](reports/20261106T221003-b19503a8c2/report.pdf) |
| games_lp | [20261106T221003-786eabcadc](experiments/20261106T221003-786eabcadc/result.json) | Knapsack 19 = oracle; zero-sum best-response gap 0 | [7](reports/20261106T221003-786eabcadc/report.pdf) |
| coding | [20261106T221004-43cff6ca83](experiments/20261106T221004-43cff6ca83/result.json) | Shortest distance 8 = exhaustive oracle | [1](reports/20261106T221004-43cff6ca83/report.pdf) |

### Paired market sensitivity

Five identical seeds per regime: `7,11,19,23,31`. Results use optimistic mock fills and final midprice marks. These are development scenarios, not a held-out official benchmark.

| Regime | Fixed mean PnL | Inventory mean PnL | Fixed worst drawdown | Inventory worst drawdown |
|---|---:|---:|---:|---:|
| market | 24.776 | 2.870 | 19.000 | 6.410 |
| market_trend | -53.008 | -0.740 | 97.240 | 11.510 |
| market_shock | -93.008 | -3.596 | 137.240 | 21.030 |

Fixed quotes lose heavily in trend/shock scenarios; inventory skew reduces these mock losses and drawdowns but does not establish profitability. No universal best strategy is established. Raw named comparisons and all experiment IDs are in `reports/index.json`.

## Exact reproduction commands

Run from the repository root:

```bash
.venv/bin/arena doctor --tests
.venv/bin/arena baseline configs/market.json
.venv/bin/arena baseline configs/ml.json
.venv/bin/arena baseline configs/ml_classification.json
.venv/bin/arena optimize configs/games.json
.venv/bin/arena optimize configs/games_lp.json
.venv/bin/arena baseline configs/coding.json
.venv/bin/arena tournament configs/market.json --seeds 7,11,19,23,31
.venv/bin/arena tournament configs/market_trend.json --seeds 7,11,19,23,31
.venv/bin/arena tournament configs/market_shock.json --seeds 7,11,19,23,31
.venv/bin/arena report 20261106T221003-b19503a8c2 --pdf
.venv/bin/arena market-features scenarios/snapshots_example.csv --kind snapshots
.venv/bin/arena market-features scenarios/bars_example.csv --kind bars
.venv/bin/arena market-features scenarios/trades_example.csv --kind trades
.venv/bin/arena inspect scenarios/snapshots_example.csv
.venv/bin/arena diagnose scenarios/snapshots_example.csv
.venv/bin/arena quick-cards
.venv/bin/arena validate-submission scenarios/one_file_example.py --contract configs/submission_contract.example.json
.venv/bin/arena package scenarios/one_file_example.py --contract configs/submission_contract.example.json --output submissions/another_rehearsal.py
.venv/bin/arena validate
.venv/bin/arena handoff
PYTHONPATH=src python3 -S -m unittest discover -s tests -q
.venv/bin/python -m pip check
```

Packaging was run with output `submissions/one_file_rehearsal.py`; rerunning that exact output intentionally fails instead of overwriting. Use a fresh output name. The example signature is unverified.

`reports/verification/commands.json` retains 26 actual CLI calls and complete outputs from the end-to-end rehearsal. `memory/validation.json` contains the latest exact test commands/output and fingerprint. Optional dependencies passed `pip check`; all ten local skill outlines passed `quick_validate.py`. PDF text/page counts were checked with pypdf, and representative market/game pages were rendered with macOS sips and visually inspected.

## Rules, security and source constraints

- Published rules require Python and permit development AI/public sources subject to Technical Rules. Exact API/scoring/runtime/dependencies/data/prepared-code restrictions still need the opening instructions. See `docs/COMPETITION_RULES.md`.
- Four principal past repositories were reviewed beyond READMEs, with pinned revisions and actual paths in `docs/SOURCE_REVIEW.md`. Historical performance claims were not reproduced. Optiver source includes AGPL; several other strategy sources had no root licence. No external strategy code was copied.
- The complete public rules application bundle is kept locally and ignored by Git; its URL and hash are recorded. No corporate files, secrets, external deployments or pushes were used. External ai-memory/hooks remain OFF.

## Remaining work and deliberate deferrals

**BLOCKED on official specification:** real adapter, exact submission signature, official evaluator/scorer, legal prepared-code/data/weights use, wall-clock/RAM/package/network limits and final submission acceptance.

**Deferred until justified:** realistic calibrated queue/market-impact execution; multiple assets/options; ranking/tree models and notebooks; timestamp-duration purging, automated feature ablations and confidence intervals; full multi-round/MDP/bandit/continuous portfolio solvers; transitive dependency bundling and a runtime sandbox. The one-round tournament example is not a full multi-round optimizer. No full ai-memory security audit was performed.

## Best next step

At the opening, obtain Technical Rules and run the untouched official sample before tuning any model. Follow `docs/ADAPTATION_REHEARSAL.md`, connect the smallest applicable baseline, and compare one change on the actual metric. Before tomorrow, learn pending-order exposure, causal feature timing, the distinction between expected score and winning probability, and why a tiny exact oracle is useful.
