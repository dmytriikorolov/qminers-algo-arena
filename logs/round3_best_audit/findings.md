# Round 3 best-run failure audit

Only round3_public.csv was replayed for this audit. The best saved round 3 run
is the adaptive maker with crash_drop=1e9 and recovery_rise=None, earning
90,650. The instrumented replay reproduces every original result field exactly.
The existing strategy retains its embedded historical model weights; this audit
does not retrain them or use earlier-round performance to select a change.

## 1. Fade inventory overrides the zero-risk sizing state

At 2616.447669 seconds (43:36), a buy of 46 lots at 9862 increases inventory
from +4 to +50. The forecast is 7.684 and the effective inventory radius is
zero, but the fade center is +50. Its one-second markout is -91 ticks/lot.
The runner subsequently holds +50 through the next drop; the PnL interval
ending at 2618.001095 loses 4,650, the worst second of the run.

This is intentional policy interaction, not a broken inventory counter:
the quote capacity formula permits moving toward the center even at radius 0.
The fade is specifically enabled while the radius is zero. Risk suppression
therefore does not mean flattening. A similar +50 fade precedes the -1,450
second at 4563 seconds. Repeated +50 exposure around 2000–2042 seconds also
contributes to the maximum PnL drawdown of 5,360.

## 2. Lowering the desired limit does not immediately lower actual inventory

At 1886 seconds inventory is +100 with radius 100. At 1888 seconds the radius
has fallen to 17 but inventory is still +100. Passive unwind fills arrive
after the market has moved; the second ending at 1888.001095 loses 1,680.
The corresponding short-inventory case around 4308 seconds loses 1,157.
An asymmetric risk/exit model should distinguish stopping new exposure from
urgently reducing existing exposure. Aggressive exits have a cost and need
an execution test before being adopted.

## 3. Inventory-growing fills have worse selection

| Actual fill group | Lots | One-second markout, ticks/lot |
|---|---:|---:|
| Increases absolute inventory | 354,329 | -0.0625 |
| Does not increase absolute inventory | 418,845 | +0.2752 |
| Cancellation already requested | 5,474 | -0.7148 |
| Other fills | 767,700 | +0.1264 |

These are quantity-weighted diagnostics of the actual fills. Overlapping
markouts are not additive realized strategy PnL, and group membership is not
a causal treatment. A flip that ends at equal absolute inventory belongs to
the non-growing group in this diagnostic.

## 4. A concrete cancellation race breaches the limit

At 408.203524 seconds, pending-cancel order u000003595 buys 60 lots at 9974,
raising inventory from +51 to +111. A rescue IOC sells the excess 11 lots.
Total breach penalty is 50, small relative to the trading losses. The order
management code releases some pending-cancel exposure before confirmation.

## Tested forecast guard

Suppress the fade center when the latest completed-second forecast exceeds
a fixed cap. The volatility forecast continues to update normally.

| Cap | PnL | First half | Second half | Max drawdown |
|---|---:|---:|---:|---:|
| Original | 90,650 | 38,605 | 52,045 | 5,360 |
| 2.2 | 85,790 | 45,304 | 40,486 | 2,784 |
| 3.0 | 86,673 | 45,363 | 41,310 | 2,734 |
| 4.0 | 77,107 | 38,122 | 38,985 | 3,827 |

The cap reduces downside but does not improve full-tape PnL. It improves the
first half at caps 2.2/3.0 and worsens the second half. The 3.0 cap is a risk
tradeoff, not a superior profit strategy. No production strategy was changed.
All experiments are exploratory on the same public tape.

The selective intrasecond guard (minimum 4 ticks, also requiring 2× forecast
RMS) earns 87,362: first half 35,953, second half 51,409, drawdown 5,143.
It also fails to improve the original. Neither guard is promoted. A guard
based on observing the jump is too late to protect inventory already held
through it; removing subsequent exposure can also miss profitable recovery.
The next test should target entry selection and the age/urgency of existing
inventory independently, with actual execution costs and the same round 3
time segments, rather than assume that fewer bad-looking fills raises PnL.

## Evidence and reproduction

fills.csv contains every fill, pre-fill controls, inventory, cancellation state,
and future markouts. decisions.csv records controls at the first callback per
second. quotes.csv records changes in the strategy's last observed two-sided
market quotes; brief one-sided-book periods retain that last observation.
pnl.csv contains the official liquidation-valued PnL curve. Cash, traded volume,
and final inventory reconcile exactly with the fill records. The simulator's
result.fills counts distinct filled order IDs, while fills.csv has one row per
partial/full execution callback.

Run `.venv/bin/python scripts/audit_round3_best.py` to reproduce the audit and
`.venv/bin/python scripts/test_round3_fade_guard.py 3` for the forecast guard.
A negative argument enables an intrasecond movement guard with the absolute
argument as its minimum jump threshold; it also requires 2× forecast RMS.
