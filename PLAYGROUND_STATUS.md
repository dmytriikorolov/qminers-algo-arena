# Playground status — 7 November 2026

## Latest dataset: sample_v2.csv

Follow-up rolling-window research: a reconstructed100-event strategy earns322;
time-thinned sampling plus returning to flat first earns1815. However, the
established maker with cap1 earns1938 with lower sampled drawdown at the same
maximum inventory1. The new `strategies/window_maker.py` is research, not a
replacement recommendation. The friend's actual code/22k score remains
unverified. See [`research/window/RESULTS.md`](research/window/RESULTS.md).

Current reviewed V2 candidate: **`strategies/v2_inventory_maker.py`**, official
full replay **+1,992 PnL**, maximum absolute inventory2, zero penalty, sampled
drawdown2. Defensive flow reproduces-30; flow LOT2/cap2 loses28,273; no-op0.
Frozen chronological increments: **620 / 690 / 682** through1800s,1800–3800s,
and the remaining stream. No candidate parameters changed after the first block.
Dataset provenance beyond the supplied CSV is unknown; these are checks on one
public tape, not proof of general profitability. The old synthetic-sample scores
below are historical and must not be compared as if the datasets were identical.

The maker quotes one lot per side, reserves pending/canceling exposure, skews
quotes against inventory, caps position at2, and cancels/liquidates on a20-unit
executable-equity drawdown trigger. It has no aggressive flow-following entry.
It loses20 and halts on the old trending sample. Gaps/missing liquidity can still
cause losses beyond the trigger; this is not a guaranteed monetary loss bound.

Backtest the current V2 file:

```bash
.venv/bin/python -m simulator.main --strategy strategies/v2_inventory_maker.py --backtest data/sample_v2.csv --log-dir logs/v2/maker-check --no-logs
```

Read [`research/v2/RESULTS.md`](research/v2/RESULTS.md) for the changed dataset,
actual exploit of defensive flow, all comparisons, reproduction and remaining
risks; [`research/v2/REVIEW.md`](research/v2/REVIEW.md) records independent review.
Submit only the standalone candidate if the team approves. No submission made.

## Earlier sample and defensive experiments

**Latest assessment after adversarial testing: no general strategy is validated.**
The 21,434-PnL flow candidate is specific to the synthetic Playground pattern.
Independent attack tapes reproduce inventory trapping and repeated spread losses.
A separate `strategies/defensive_flow.py` adds confirmed small entries, independent
exits, cooldown and a drawdown halt. It reduces tested losses but still loses in
adverse regimes; its sample PnL 730 is followed by permanent shutdown at 634.5s.
See [`DEFENSIVE_RESULTS.md`](research/playground/DEFENSIVE_RESULTS.md) and
[`DEFENSIVE_REVIEW.md`](research/playground/DEFENSIVE_REVIEW.md).
Do not infer real-market readiness or immunity from exploitation from either file.

Original frozen Playground candidate: **`strategies/playground_flow.py`**.
Official-simulator PnL **21,434**, compared with **1,878** for the untouched
example. Zero breach penalties; maximum absolute inventory **20**. Independent
review found no blocking state/accounting defect; see
[`research/playground/REVIEW.md`](research/playground/REVIEW.md).
No strategy has been submitted. Deadline supplied by the team: **12:00 Prague
on 7 November 2026 (11:00 UTC)**.

## Available material and verified contract

- Untouched official simulator, example/template, explorer, Python 3.13.16 venv
  and the exact README-pinned numerical packages. Provenance and hashes are in
  [`research/playground/provenance.json`](research/playground/provenance.json).
- Organizer-provided `data/sample.csv`: synthetic 3599-second tape, 53,758 rows,
  26,578 resting inserts, 604 IOC inserts, 26,576 cancels. The supplied briefing
  PDF explicitly says this sample is also the dashboard Playground download;
  the team confirmed this is the organizer-provided data. No recorded-market
  round or private backtest is present. Dataset hash/profile:
  [`data_profile.json`](research/playground/data_profile.json).
- `_prep/MORNING_HANDOFF.md`, market feature/risk source, critical review and
  paired research results were reviewed as references. Their mock performance
  numbers do not establish official performance. `_prep/` was not modified.
- Official callbacks: one `BaseStrategy` subclass with no constructor arguments;
  `on_order_book_change(snapshot, trades)` and `on_private_order_update(event)`.
  Prices and quantities are positive integer ticks/lots. Sends return an ID
  immediately. Every action waits 5ms; the engine activates due actions against
  the prior book before processing the next market event. Private event times
  are the scheduled ready times, including on sparse tapes. EOF drains pending
  actions. Use only private per-match fills for inventory accounting.
- Price/time matching; IOC residuals cancel; own orders never match each other.
  Snapshots contain individual market AND user orders within 20 **ticks**, not
  20 levels. Our signals use only market orders and market-vs-market trades.
- Acceptance rejects `abs(I + sign*(resting_same_side + new_quantity)) > 1000`.
  That is not the safe inventory limit: holding `abs(I)>100` costs 10,000 per
  second. Pending orders and in-flight cancels must retain risk reservations.
  Candidate uses one IOC in flight and a strict internal limit of 20.
- Per-replay score = cash + full-depth market-book liquidation value − penalty.
  It is not midpoint marking. Fills count distinct filled order IDs. The public
  [Arena information page](https://arena.qminers.com/dashboard/info) describes
  final competition scoring as `0.8*z1 + 1.0*z2 + 1.0*z3 + 1.2*z4` using private
  backtests; nonpositive teams are excluded from each round's mean/std and
  treated as zero PnL. Local Playground PnL is not that final combined score.
- Submission: one `.py` ≤1 MiB, 1 CPU, 2GB RAM, 15 minutes, no network. Imports
  restricted to permitted standard library/numerical packages and public
  simulator models/BaseStrategy. System/file/thread/introspection modules,
  `open/eval/exec/getattr/type`, dunder access except allowed initialization,
  and `str.format` are prohibited. Our candidate imports only public API types
  and BaseStrategy; local screening passes. The actual server validator is not
  bundled here, so server acceptance remains unverified. No extra dependency
  is needed by either standalone strategy.

## Reused preparation and resulting strategies

`playground_quotes.py` adapts top-touch imbalance/microprice, causal volatility
estimation, inventory skew, small caps and pending/cancel exposure reservations.
It aggregates all individual market orders at the touch. It does **not** reuse
the mock ledger, fill model, old decimal price scale, or old performance claims.
This quoting approach underperformed and is retained as research only.

The selected `playground_flow.py` uses the official example's directional trade
flow/alternation idea with private-fill inventory accounting, terminal IOC
handling, filtering of own trades, spread guard, explicit sizing and a cap of
20. It holds one order slot through acceptance and partial fills until a terminal
event. The supplied example omits clearing its busy flag on cancellation;
the briefing PDF describes that exact correction. We preserved the original.

## Measured results

| Policy / dataset | PnL | Filled orders | Volume | Final inventory | Max abs inventory | Penalty |
|---|---:|---:|---:|---:|---:|---:|
| No-op / full sample | 0 | 0 | 0 | 0 | 0 | 0 |
| Official example / full sample | 1878 | 305 | 305 | -1 | 1 | 0 |
| Selected flow LOT20 / full sample | **21434** | 301 | 3430 | -4 | 20 | 0 |
| Quotes default / full sample (initial run) | 8 | 42 | 84 | 0 | 4 | 0 |

Candidate cash 61,586 and liquidation liability 40,152 reconcile to PnL 21,434.
It has 243 partial fills followed by residual IOC cancellation and 58 full
fills, no rejects; minimum measured send-to-fill latency 5ms. Its time-weighted
absolute inventory q50/q68/q95/q99.7 is 8/12/20/20; sampled maximum drawdown 554.
The baseline's sampled maximum drawdown is 16, so the PnL gain carries materially
more risk. The gain mostly scales the same synthetic signal rather than adding
validated prediction features.

Predefined sizing/feature sweep used the first 40 minutes. LOT20 was frozen
before evaluating its final 20 minutes. Continuous candidate block PnLs:
7,951 / 8,484 / 4,999; official baseline: 644 / 615 / 619. Initial one-lot and
quoting full-sample results had already been inspected, so the final block is
a post-freeze sizing check, not wholly unseen strategy-family validation.
Full records, failed ideas and reproduction commands:
[`EXPERIMENT_LOG.md`](research/playground/EXPERIMENT_LOG.md).

## Exact commands

From the repository root, use the existing venv:

```bash
.venv/bin/python -m simulator.main --strategy strategies/playground_flow.py --backtest data/sample.csv --log-dir logs/playground/candidate --no-logs
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m scripts.check_playground_submission strategies/playground_flow.py strategies/playground_quotes.py
```

Equivalent official entry point after `uv sync`:

```bash
uv run exchange-simulator --strategy strategies/playground_flow.py --backtest data/sample.csv --log-dir logs/playground/candidate --no-logs
```

The exact file for the original 21,434 Playground result is
**`strategies/playground_flow.py`**. The defensive experiment is a different file;
it is not a replacement with the same score. Any submission must contain only
the chosen standalone strategy, not scripts, research or `_prep/`.
Full explorer logs were generated at
`logs/playground/candidate_full_logs`; omit `--no-logs` to regenerate them.

## Critical risks and next experiment

This is a reviewed, profitable **synthetic Playground candidate**, not a proven
recorded-market strategy. No independent recorded dataset, private test, actual
server static check, or server resource measurement has been available. The
sample deliberately continues in trade direction; that edge may vanish or
reverse in later rounds. Partial fills leave inventory exposed until opposite
flow; no stop-loss or clock-driven flattening is implemented. End inventory is
valued by the official sweep. Larger size increases drawdown and liquidity use;
do not raise the cap on the strength of this tape.

**Next useful experiment:** when the first recorded round arrives, freeze this
candidate and compare it with LOT1, no-op, and the retained quoting candidate on
the identical full stream and chronological blocks. Measure adverse markouts,
IOC miss rate, liquidity and drawdown before changing any parameters. Do not
spend more Playground time retuning the failed quoting variants on this sample.

Work is isolated on `feature/playground-official-adapter`. Simulator/starter
files and existing teammate changes are preserved. No push, merge, submission,
or third-party memory tool installation was performed. A PDF text reader was
installed only in `/private/tmp`, outside project dependencies.
