# Adversarial follow-up: protection is not established alpha

The original 21,434 sample PnL does not establish a good general strategy.
The sample rewards directional trade following; LOT20 amplifies that specific
pattern. Hard position accounting prevents inventory penalties, but it does
not prevent adverse selection, paying spreads repeatedly, or trapped exposure.
The tape is fixed and does not react to the strategy: the official simulator
does not contain an adaptive adversary trading against this particular bot.
We test misleading signals and hostile market paths instead.

## Independent original-strategy counterexamples

The reviewer created official-engine tapes before the new implementation:

| Tape | Original LOT20 PnL | Failure |
|---|---:|---|
| Immediate reversal, no opposite flow | -240 | Holds 20 indefinitely |
| Liquidity disappears and returns much lower/thinner | -1340 | Cannot exit, still holds 20 |
| 100 rapid alternating market signals | -2000 | Trades 2000 units paying the spread |

Exact reproducible cases and assertions are in
`tests/test_playground_adversarial.py`. Existing mechanics tests alone had not
exposed these economic weaknesses. The original candidate is preserved intact.

## Separate defensive candidate

`strategies/defensive_flow.py` is a standalone permitted-import experiment:

- Flat-only entries, LOT2/cap5 (actual possible entry exposure at most 2), limited
  displayed-touch participation. One IOC in flight; private fills update cash
  and position, and partial/canceled orders are reconciled.
- A market trade arms a direction. Entry requires at least 100ms and a subsequent
  >=1-tick move in that direction within 2s. Displayed depth alone cannot trigger
  an entry. This is a heuristic against an isolated false signal, not proof
  that price confirmation identifies informed flow.
- Exits need no opposite trade signal. A 5s holding timeout starts at the first
  actual fill; a 12-unit trade loss or 30-unit peak equity drawdown triggers exit.
  Equity uses visible executable market liquidity, not midpoint.
- IOC liquidation can use one-sided liquidity and partial fills; missed exits
  retry no faster than 100ms. There are no timers: all decisions need callbacks.
- After flattening, a 1s cooldown limits churn. A 30-unit drawdown permanently
  disables new entries for that replay while continuing liquidation attempts.

**Loss thresholds are triggers, not bounds.** The independent missing-liquidity
test enters 2 lots through valid confirmation, cannot exit during the missing
book, then liquidates one lot at each returning bid. PnL is -133 despite a 12-unit
loss trigger. Jumps, 5ms latency, missing callbacks and missing executable volume
make guaranteed loss limits impossible for this implementation. Once halted,
no automatic recovery or rearming is implemented.

## Public sample comparison

| Policy | PnL | Max abs inventory | Sampled max drawdown | Behavior |
|---|---:|---:|---:|---|
| Original LOT20 | 21434 | 20 | 554 | Narrow synthetic pattern |
| Original flow LOT2/cap2 control | 3756 | 2 | 32 | Same original logic at smaller size |
| Defensive | 730 | 2 | 28 | Halts at 634.503702s; flat thereafter |
| No-op | 0 | 0 | 0 | No exposure |

Defensive volume 208, 104 filled order IDs, 116 submissions, zero penalty.
Continuous 20-minute block PnLs 730/0/0: the circuit breaker ended the experiment
after about 10m34s. Do not present zero later losses as continued successful
trading. Its threshold 30 can trigger inside a second although sampled drawdown
is 28. No defensive threshold was tuned after these results.

## Fixed stress comparison

Official engine, identical per-policy tapes, 30 cycles per tape, seeds 101–104.
Parameters were frozen in `DEFENSIVE_SELECTION.md` before these stress runs.
Each table entry is mean PnL over four seeds; full rows/hashes are in
`defensive_stress.json`. These are invented stress paths, not recorded-market
validation or independent alpha estimates.

| Regime | Original20 | Flow2 control | Defensive | No-op |
|---|---:|---:|---:|---:|
| Continuation | 1150 | 115 | 10 | 0 |
| Reversal after confirmation | -1795 | -179.5 | -37.5 | 0 |
| Large gap after confirmation | -15050 | -1505 | -121 | 0 |
| Thin liquidity | -355 | -35.5 | -34 | 0 |
| Imbalanced displayed depth / price changes, no trades | 0 | 0 | 0 | 0 |

The cap-only control shows much of the original risk is simply size. Extra
defensive logic further reduces losses in these reversal/gap cases, while
giving up continuation gains. It still loses, and no-op wins the adverse cases.
The constructed cases and four seeds are a narrow diagnostic, not a minimax
guarantee against other paths or adaptive manipulation.

## Commands and decision

```bash
.venv/bin/python -m simulator.main --strategy strategies/defensive_flow.py --backtest data/sample.csv --log-dir logs/playground/defensive-check --no-logs
.venv/bin/python -m scripts.defensive_stress
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m scripts.check_playground_submission strategies/defensive_flow.py
```

There are now 17 passing integration tests, including 11 independent adversarial
tests. Passing tests establishes the tested mechanics; it does not establish
the missing trading edge. Do not replace the preserved Playground artifact
with this lower-PnL experiment while claiming a superior general strategy.
Next: collect recorded official data and estimate causal flow markouts net of
spread and 5ms latency on chronological out-of-sample intervals. Keep LOT1/2
controls and no-op; require positive, stable cost-adjusted results before
promoting prediction features or raising risk. No push or submission performed.
