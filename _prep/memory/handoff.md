# Local handoff

Generated: 2026-11-07T08:55:56.677413+00:00
Branch: dima; commit: c4df2d49a88efb6f251ef45c9af63accf695658d; dirty: True

## Verification

Local validation passed: True at 2026-11-07T08:55:16.077462+00:00.
Evidence matches current code and tests: True.
See memory/validation.json for exact commands and complete output. Rerun after changes.

## Recent saved results

- market `20261106T221006-dd37beda7b`: {"best_pnl": 2.30999999999991, "best_strategy": "momentum", "steps": 300, "strategies": 8}
- market `20261106T221006-90e7451064`: {"best_pnl": 7.79000000000009, "best_strategy": "momentum", "steps": 300, "strategies": 8}
- market `20261106T221006-b0f3354d84`: {"best_pnl": 97.72, "best_strategy": "momentum", "steps": 300, "strategies": 8}
- market `20261106T221007-eaa73289d3`: {"best_pnl": 28.88, "best_strategy": "momentum", "steps": 300, "strategies": 8}
- market `20261106T221007-6808851379`: {"best_pnl": 4.85, "best_strategy": "signal", "steps": 300, "strategies": 8}
- market `20261106T221007-6c6909587a`: {"best_pnl": 34.30999999999991, "best_strategy": "momentum", "steps": 300, "strategies": 8}
- market `20261106T221007-1fd719cc85`: {"best_pnl": 27.99000000000009, "best_strategy": "momentum", "steps": 300, "strategies": 8}
- market `20261106T222130-72f04f1e23`: {"best_pnl": 29.36, "best_strategy": "fair_value", "steps": 300, "strategies": 9}

Results are scenario-specific; no universal best strategy is established.

## Reproduce

```bash
# Run from the repository root
.venv/bin/arena doctor --tests
.venv/bin/arena baseline configs/market.json
.venv/bin/arena baseline configs/ml.json
.venv/bin/arena optimize configs/games.json
.venv/bin/arena baseline configs/coding.json
.venv/bin/arena validate
```

## Next three actions

1. Read Technical Rules and run the official sample unchanged
2. Implement the exact adapter/signature and official scorer
3. Compare a minimal baseline and one improvement on legal held-out cases

## Restrictions

- Preparation only; no verified submission contract
- Synthetic fills are not live profits
- Third-party AI memory and hooks remain OFF
- No push or deployment authorized

## Failures and decisions

See memory/failures.md and memory/decisions.md.

## All four families and reports

Full run inventory and paired regime results: `reports/index.json`; concise verified status: `TONIGHT_STATUS.md`.

- market: `20261106T221002-7b7a75883e`, PDF `reports/20261106T221002-7b7a75883e/report.pdf`.
- ml: `20261106T221002-c689560b39`, PDF `reports/20261106T221002-c689560b39/report.pdf`.
- ml_classification: `20261106T221002-40ff7ef576`, PDF `reports/20261106T221002-40ff7ef576/report.pdf`.
- games: `20261106T221003-b19503a8c2`, PDF `reports/20261106T221003-b19503a8c2/report.pdf`.
- games_lp: `20261106T221003-786eabcadc`, PDF `reports/20261106T221003-786eabcadc/report.pdf`.
- coding: `20261106T221004-43cff6ca83`, PDF `reports/20261106T221004-43cff6ca83/report.pdf`.

## Superseding readiness pass

Read `MORNING_HANDOFF.md` first. Quote tick arithmetic was corrected; old trading results are historical. Latest validation: 187 tests passed. Independent review and four-regime capped-risk comparisons are in `reports/critical_review.md` and `reports/trend_guard_validation.json`. Code checkpoint `aa1227a`; overnight preparation remains disabled.

## Repository layout

The toolkit now lives directly in the repository root. Run all commands here; no nested launch directory is needed. Latest root validation: 187 tests passed.
