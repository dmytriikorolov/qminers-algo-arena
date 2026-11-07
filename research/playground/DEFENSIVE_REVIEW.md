# Independent defensive review

Verdict: the candidate has tested defensive mechanics and reduces losses on the
specified attacks. This does **not** establish a profitable general edge, a hard
loss bound, or immunity to exploitation. No blocking state-management defect was
found in the final risk code.

## Independently reproduced evidence

- All 17 review/adversarial integration tests pass, including legitimate
  confirmed long/short entries, reversal exits without opposite flow, timeout
  measured from actual fill, cooldown, drawdown halt, partial exits, missing
  liquidity, and stale exit IOC retry.
- Official sample CLI reproduces PnL730, volume208, final inventory0, penalty0.
  An independent callback observer confirms first halt at634.503702 seconds.
  Later blocks are zero because trading halted; they do not demonstrate ongoing
  stability. The size-matched flow2 control earns3756 with sampled drawdown32.
- All 80 stress records were independently replayed directly through the
  official engine. PnL, volume, final inventory, penalty, generated-tape hashes,
  and strategy hashes match the recorded results.

Mean stress PnL over four seeds:

| Regime | Original20 | Flow2 control | Defensive |
|---|---:|---:|---:|
| Continuation | 1150 | 115 | 10 |
| Reversal | -1795 | -179.5 | -37.5 |
| Gap | -15050 | -1505 | -121 |
| Thin | -355 | -35.5 | -34 |
| Depth only | 0 | 0 | 0 |

The size-matched control is essential: reducing size already removes much of the
original strategy's loss. Additional defenses help reversal/gap cases but barely
improve the thin case and sacrifice most continuation gains. No-op earns zero in
every regime. Lower tested losses alone do not justify taking these trades.

## Generator and risk traps

The generator uses fixed scheduled quote replacements, synthetic directional
confirmation, independent seeded directions, and five hand-designed regimes.
It gives every policy identical tapes and distinguishes continuation, adverse
moves, thin depth, and depth imbalance without trades. This is useful mechanical
stress coverage, not market calibration or an independent market holdout. Four
seeds per regime and 30 cycles do not establish tail-risk coverage. The separate
missing-book tests cover an absence of liquidity not represented by merely
setting stress depth to one.

Risk exits are independent of entry flow/spread and use executable visible
market depth, with one order pending and actual private fills tracked. Temporary
empty snapshots preserve a pending signal; entry still requires a valid book
and unexpired signal. A trade-loss trigger12 and drawdown trigger30 are **not**
guaranteed bounds: confirmed-entry tests realize -28 after a jump and -133 when
bids disappear and return thin. Partial visible depth yields no complete equity
mark; exposure remains until executable liquidity returns. Exits can miss after
5ms latency and retry later. Timeouts/retries require market callbacks, so a
quiet tape can delay them. Liquidation at EOF also differs from achieving an
actual exit. Sampled one-second drawdown28 does not contradict an intrasecond
halt at30.

The sample was already examined during development, and its transient-book
signal handling was corrected after observing zero entries. The freeze record
discloses this. No independent recorded-market profitability validation exists.

Reproduce from repository root:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_playground*.py' -v
.venv/bin/python -m simulator.main --strategy strategies/defensive_flow.py --backtest data/sample.csv --log-dir /private/tmp/qminers-defensive-review --no-logs
```
