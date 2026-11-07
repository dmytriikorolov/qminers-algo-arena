# Rehearsal: adapt the tested toolkit to an official task

Run commands from the repository root. Timings are a work budget, not a guarantee of solving an unknown task. Synthetic practice is available now; official integration depends on the organisers' Technical Rules/API.

## Minutes 0–5: reproduce the local foundation

```bash
.venv/bin/arena doctor --tests
.venv/bin/arena inspect configs/market.json
.venv/bin/arena diagnose configs/ml.json
```

If the virtual environment is absent, use the installation commands in the project quick start first. Read `COMPETITION_RULES.md` and update every applicable unknown from the released Technical Rules. Assign one owner to scoring/rules and one to the official sample/adapter. Python and broad AI/research permission are published; runtime, libraries, pre-event artifacts, final format and scoring details still require confirmation.

## Minutes 5–10: run the official sample unchanged

Use the exact command supplied by organisers. Record its version, command and output. Do not invent a 2026 `Model.place_bets` or `Trader.run` interface from earlier contests.

Write down the controlled action, exact metric, units, limits, input availability times and expected output. Compute one tiny case by hand. Decide the task family using `TASK_CLASSIFIER.md`.

## Minutes 10–20: connect one baseline

Choose only the matching row. The commands below exercise preparation examples; they do not connect to an official exchange.

| Family | Runnable rehearsal | Adaptation point |
| --- | --- | --- |
| Market/exchange | `.venv/bin/arena baseline configs/market.json` | `src/arena/trading.py`: causal features, ledger and simple strategies. Replace mock events/fills with a separately named official adapter only after verifying callback semantics. |
| Numeric labelled data | `.venv/bin/arena baseline configs/ml.json` | `src/arena/ml.py`: `run_csv` with explicit target, time and features. Use actual legal data and official metric. |
| Allocation or strategic game | `.venv/bin/arena optimize configs/games.json` | `src/arena/games.py`: write the actual payoff/constraints, then compare a tiny oracle with the faster solver. |
| Coding/automation | `.venv/bin/arena baseline configs/coding.json` | `src/arena/algorithms.py`: select an applicable primitive and preserve the official input/output signature. |

For a real ML CSV kept inside the project, create a JSON config with this shape, replacing the example names with inspected columns:

```json
{
  "family": "ml",
  "seed": 7,
  "dataset": "data/official_training.csv",
  "parameters": {
    "target": "answer",
    "features": ["known_feature"],
    "time_column": "timestamp",
    "task": "regression",
    "gap": 1,
    "label_horizon": 1
  }
}
```

Save as `configs/official_ml.json`, then run `.venv/bin/arena inspect data/official_training.csv` and `.venv/bin/arena experiment configs/official_ml.json`. `task="classification"` supports binary 0/1 targets. Set gap/horizon from actual label timing, not this example. Times must increase strictly; resolve ties explicitly. An optional `group_column` checks cross-split overlap; it does not automatically design a group split. Chronology and a direct-copy check cannot prove every feature is legal or causal.

For market CSVs, `.venv/bin/arena market-features data/official_snapshots.csv --kind snapshots` computes causal features after verifying its explicit schema; `--kind bars` and `--kind trades` use their own required columns. This does not replay own orders or infer fills. See [MARKET_DATA.md](MARKET_DATA.md) for supported schemas.

For market integration, separately test fee signs, partial/duplicate fills, pending exposure, cancel races, stale messages, tick/lot sizes and final valuation. The mock replay is not the official scorer. For matrix games inspect the reported exploitability gap; the default solver approximates zero-sum equilibrium. An explicit optional SciPy primal/dual LP is also available when installed and permitted; neither method solves a general-sum game.

## Minutes 20–25: compare and save evidence

The following practice commands save a real run and create a report from its ID:

```bash
arena_rehearsal_id=$(.venv/bin/arena experiment configs/ml.json | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
.venv/bin/arena report "$arena_rehearsal_id" --pdf
.venv/bin/arena tournament configs/market.json --seeds 7,11,19
```

PDF generation needs the reports extra; HTML/Markdown reports remain available without `--pdf`. These seeded examples establish local reproducibility and sensitivity, not official profit. Run the official scorer on the candidate separately and preserve its exact artifact/result. Change one idea at a time and keep a final holdout untouched.

## Minutes 25–30: preflight and preserve a baseline

```bash
.venv/bin/arena validate
.venv/bin/arena handoff
```

The supplied `configs/submission_contract.example.json` is illustrative and unverified. Once the real contract is known, prepare a separate JSON contract and run:

```bash
.venv/bin/arena validate-submission submissions/candidate.py --contract configs/official_contract.json
```

Current static preflight checks a top-level synchronous function, positional parameters, source size and declared imports. It does not validate an organiser's class-based interface, execute code, enforce runtime/memory, certify absence of side effects, or establish eligibility. Run official samples under actual limits before submitting. Preserve the last accepted artifact and its SHA-256. Read `memory/handoff.md` before the next change.

## What to learn first

Be able to explain the score, the data available at each decision, the worst-case legal exposure/budget and the smallest baseline's failure cases. Understanding those four facts is more useful at the opening than adding another framework.
