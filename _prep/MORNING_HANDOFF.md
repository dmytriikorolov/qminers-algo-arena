# Morning handoff — 7 November 2026

Code checkpoint: `aa1227ae7c91fd45ca2a6dcf35f49aa4f6bf35ae` on `main`. All changes are local. Use `git log -2 --oneline` for the final evidence commit. Latest validation: **187 tests passed** (181 toolkit + 6 starter), no failures or optional skips in the venv. Standard-library-only run: 176 tests OK, five optional skips. `pip check` and CLI doctor/market baseline passed.

## 1. What actually works

Offline `arena` CLI; deterministic market simulation/accounting; causal CSV snapshot/bar/trade features; chronological ridge/logistic ML; six game examples and graph solvers; experiment provenance, reports and static one-file packaging. These are preparation tools. No official strategy adapter, scorer or submission contract has been verified.

## 2. What was independently checked

A reviewer with fresh context read code and artifacts rather than accepting the status report. Strongest/weakest fixed and momentum runs reproduced exactly before the fix. A separate Fraction cash-flow/position oracle checked 2,000 executions, partial fills, position flips, fees/rebates and duplicates; no accounting defect was reproduced. ML test/feature perturbations did not affect fitting or validation selection. The reviewer ran 61 focused tests and private seeds 901–905 in five regimes.

The reviewer found a real one-tick quote-widening bug caused by float arithmetic before Decimal rounding. A regression test failed, then passed after Decimal midpoint and quote arithmetic replaced the affected operations. **Old numerical performance reports are historical and must not be compared with current code without rerunning.** Full verdict/data: `reports/critical_review.md` and `.json`.

## 3. Best strategy and limitations

There is **no generally best profitable strategy**. No-op remains the zero-exposure benchmark; it beats guarded quotes on every independent stress-regime average. If the official task requires quoting, use a small inventory-aware baseline, beginning with a reduced position limit, and evaluate it officially before trusting it.

`guarded_fixed` is an opt-in risk experiment: soft inventory cap five, fixed anchor restricted to within one price unit of current mid, and inventory skew. It does not replace defaults. It reduced worst drawdown versus fixed limit ten in all four root test regimes and all five reviewer regimes. Most protection is explained by halving exposure. The simple fixed-cap-five control often matches or beats its PnL; the guard gives up mean-reverting upside and still loses under trends. No settings were searched on the new holdout seeds.

Root paired comparison: 20 fresh seeds 101–120, 300 steps each, fee 0.01, same data per policy. Mean PnL / worst marked drawdown:

| Regime | Fixed limit 10 | Fixed limit 5 control | Guarded fixed | Inventory quotes |
|---|---:|---:|---:|---:|
| mean_reverting | 28.707 / 18.26 | 17.325 / 10.02 | 16.544 / 8.50 | 2.573 / 11.27 |
| trend | -68.815 / 145.00 | -34.635 / 72.50 | -33.545 / 71.16 | -2.613 / 17.58 |
| trend_down | -65.795 / 125.80 | -33.070 / 63.05 | -32.503 / 64.56 | 0.112 / 16.87 |
| volatile | 12.855 / 202.90 | 5.839 / 104.66 | 0.791 / 107.65 | -26.515 / 73.56 |

Raw paired results, actual dataset hashes and estimated bid/ask liquidation costs: `reports/trend_guard_validation.json`. Acceptance is for lower worst drawdown and capped exposure, **not profit dominance**. Positive mock returns are not live edge; front-of-queue fill priority, no impact and mid marking remain optimistic assumptions.

## 4. Critical unresolved risks

- Official API, scoring, runtime/dependencies, final valuation, permitted prepared code/data/weights and exact constraints remain unknown. Fresh public-rule check at 23:17:40 Prague found unchanged rules, which defer Technical Rules to the opening. See `docs/COMPETITION_RULES.md`.
- `Ledger.submit` and exposure checks scan all historical orders. Reviewer timings scale approximately quadratically: 1k/2k/4k steps took .184/.630/2.331 seconds. The 300-step sweeps are bounded; **do not treat this as a production live-session ledger**. Match the real simulator first, then track active orders separately if long sessions require it.
- Cancellation acknowledgements are explicit fill barriers in our mock contract. A real API with different event ordering needs reconciliation, not blindly calling these handlers.
- Chronological ML splitting cannot detect semantic future features or all transformed target leakage. Repeated holdout tuning creates selection bias.
- Fixed-cap-only is often as good as the new guard; additional guard complexity is not established edge. Negative stress PnL remains a failed profitability result, not something to conceal by selecting the best path.

## 5. Exact commands for the morning

From the repository root:

```bash
# Run from the repository root
.venv/bin/arena doctor
.venv/bin/arena validate
.venv/bin/python scripts/validate_trend_guard.py
.venv/bin/arena baseline configs/market.json
.venv/bin/arena baseline configs/ml.json
.venv/bin/arena baseline configs/ml_classification.json
.venv/bin/arena optimize configs/games.json
.venv/bin/arena optimize configs/games_lp.json
.venv/bin/arena baseline configs/coding.json
.venv/bin/arena inspect scenarios/snapshots_example.csv
.venv/bin/arena market-features scenarios/snapshots_example.csv --kind snapshots
```

`python3 arena doctor` and `python3 arena baseline configs/market.json` work without the optional venv packages. Optional LP/PDF commands require the venv. `git status --short` and `git log -2 --oneline` establish branch/checkpoint; do not reset changes blindly.

## 6. First 30 minutes of the hackathon

- **0–5:** obtain Technical Rules, sample and exact evaluator; record versions, allowed code/data/AI, resource limits and submission deadline. Use `docs/MORNING_INTEGRATION_CHECKLIST.md`.
- **5–10:** run the untouched official sample. Save exact command, output and score. Identify task family; agree on controlled actions and metric.
- **10–20:** one owner connects only the smallest appropriate baseline to the actual signature. Hand-check scoring, timing, costs, limits and empty actions. For trading, test fills/cancels/pending exposure before signal changes.
- **20–25:** compare one candidate against the untouched baseline using the official scorer and legal held-out cases. Check startup/runtime/memory.
- **25–30:** freeze and preserve the exact legal artifact/hash and score. Submit through the authorised team flow only when allowed; record actual acceptance. Keep a known-good rollback. Do not implement an invented adapter tonight.

## 7. Four module readiness

| Module | Ready now | Still needs official integration |
|---|---|---|
| Market understanding | Mock ledger, nine policies, risk tests, causal CSV features | Real fills, callback ordering, legal actions, live scaling, scorer |
| Machine learning | Mean/ridge and constant/logistic; train-only preprocessing and chronological checks | Actual target/features/metric/data rights; irregular-label purging if needed |
| Game theory/strategy | Six stated toy problems, knapsack oracle/DP, approximate and optional LP matrix game | Actual objective/opponents/constraints; no full multi-round optimizer |
| Coding/automation | Tested graph/search primitives, CLI, provenance and static packaging | Exact judge signature, allowed imports and resource enforcement |

All four are usable offline starting points; none is an officially verified submission.

## 8. If Codex usage is exhausted

Stop adding features. Read this handoff, `docs/MORNING_INTEGRATION_CHECKLIST.md`, and `docs/QUICK_CARDS.pdf`. Use the existing tests and CLI without AI. Assign one human to integration and one to evidence/risk. Keep the official baseline intact and change one thing at a time. If uncertain, prefer the smallest valid solution and organiser clarification over an untested rewrite. No external ai-memory or global hooks are needed.

### Optional overnight work

`scripts/overnight_sweep.py` is prepared and tested, **not enabled or scheduled**. It calls no models/services, makes no submissions and writes only ignored `overnight_runs/`. Caps: 240 replays, 300 steps each, one active job, 20-minute active timeout; scheduled waiting mode ends before 07:00 Prague. Source changes abort it. It never updates tracked source, memory or experiments. Details and optional manual one-time 02:00 command are in `docs/OVERNIGHT.md`. It does not need or assume more AI credits. You may simply skip it; the readiness pass already covers independent held-out cases.
