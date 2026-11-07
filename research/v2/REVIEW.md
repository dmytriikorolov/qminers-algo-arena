# Independent V2 review

The old defensive flow fails on the changed tape. An independent official CLI
reproduces **PnL -30**, volume 36, 18 filled orders, flat final inventory and zero
breach penalty. Its entries are poor here; no position or cash accounting defect
was found. The new small maker performs better on this particular tape, with
credible mechanics tests, but has no guaranteed loss bound or established
profitability on other markets.

## Actual defensive loss and a remaining exploit

In the first 300 seconds, the nine completed trades earn
`-6, +2, 0, -2, -4, -4, -4, -6, -6`. The first eight exit after the five-second
holding timeout. The ninth triggers portfolio drawdown 30 at 173.387931 seconds
and closes at 173.392931 seconds. Peak liquidation equity never exceeds zero.
The first trade buys 2 @ 10002 at 2.098455 seconds and sells 2 @ 9999 at
7.104295 seconds. Spread crossing and weak continuation confirmation explain the
loss. On this identical prefix, independently replayed flow2/cap2 loses 1508
(volume 1758, final inventory 2); no-op earns zero.

New `tests/test_v2_risk.py` demonstrates an ask-removal bait with the bid fixed
at 100. A buy trade at 102 arms the old signal; replacing ask 102 with 104 raises
the midpoint by one without improving the executable selling price. The default
defensive strategy confirms and buys 2 @ 104, then exits at 100: PnL -8. The
size-matched flow control loses 4 and no-op loses zero. Repeating the bait causes
four round trips and a permanent halt at -32, beyond its drawdown trigger 30,
even without a price gap. Entry costs can consume the remaining risk budget.

## Independent maker verification

The independent official full CLI exactly reproduces **PnL 1992**, cash 11996,
inventory -1, liquidation mark 10004, 2529 fills/volume, and zero breach penalty.
Arithmetic: `11996 - 10004 = 1992`. Source/data hashes match `maker_final.json`.
An independent validation-prefix CLI reproduces 1310.

Independent full-run PnL samples give continuous split marks 620 at 1800 seconds
and 1310 at 3800 seconds: validation increment 690 and final increment 682.
Both prefix EOF versus continuous boundary differences are zero. Maximum
one-second sampled drawdown is 2; it does not measure every intrasecond loss.
The recorded maximum inventory and reserved exposure are both 2. The maker did
not halt on this tape. A separate full-run observer confirms all 31 rejections
were `cancel rejected: no resting order with this id`; none were potential-
position or new-order rejections. These are delayed cancels racing terminal
orders.

The fresh test suite passes **23 tests**, including six new V2 tests. Maker tests
confirm that an opposite-side fill during cancel flattens without an unnecessary
IOC, a same-side partial fill during cancel increases the eventual IOC from 1 to
2 correctly, and a halted maker retains inventory while bids are absent before
exiting when they return. Private cash/inventory reconcile with the engine;
quote and pending exposure stay within the cap. No blocking order-state defect
was found.

## Limits and evaluation discipline

Drawdown 20 is a trigger, not a guaranteed monetary bound. The missing-liquidity
test realizes -60. Incomplete visible depth prevents a complete equity mark;
absent callbacks delay risk decisions, and no separate maker timeout forces an
exit while its drawdown cannot be computed. Cancellation and submission each
carry latency. Startup quoting uses whichever book has been built so far, with
no warm-up. The old sample makes this maker lose 20, showing regime dependence.

`SELECTION.md` freezes parameters before continuous validation and the final
check. Development controls used the first 1800 seconds. The user's full
defensive result and public tape were already observed, so later blocks do not
make this research wholly independent. This reviewer did not assess maker
last-third performance before the freeze. Tape provenance is unknown; the
friend's reported strategy is unavailable and its loss was not reproduced.

The narrow verdict is to prefer the capped maker over the failed flow on V2,
while preserving the other candidates and the explicit no-op alternative. This
is not evidence of immunity to exploitation or a general market edge.

Reproduce from repository root:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m simulator.main --strategy strategies/defensive_flow.py --backtest data/sample_v2.csv --log-dir logs/v2/reviewer_defensive --no-logs
.venv/bin/python -m simulator.main --strategy strategies/v2_inventory_maker.py --backtest data/sample_v2.csv --log-dir logs/v2/reviewer_maker --no-logs
```
