# Rolling-window comparison

This is a reconstruction of the user's description, not the friend's actual
strategy. That file and its sizing/quote rules were unavailable; the reported
22k cannot be reproduced or compared fairly from prose alone.

Same `data/sample_v2.csv`, official5ms engine/limits/scoring. No original
strategy, simulator or `_prep/` files were changed. First1800s development:

| Variant, LOT1/cap2 | PnL | Sampled drawdown | Max abs inventory |
|---|---:|---:|---:|
| Mean of100 valid book events | 90 | 4 | 2 |
| Event mean, reduce existing inventory first | 93 | 1 | 1 |
| Mean of100 samples at least100ms apart | 172 | 21 | 2 |
| Thinned mean plus reduce first | 563 | 3 | 1 |

Selected the last variant before full comparison; no further parameter tuning.
See `SELECTION.md`. Its source is `strategies/window_maker.py`: rolling sum/deque,
100 valid market-only midpoint samples, minimum100ms between retained samples,
one globally outstanding order including in-flight sends/cancels, LOT1/cap2,
20-unit drawdown halt. Normal entry posts at current bid/ask, with side selected
by mean reversion; existing inventory takes priority and is reduced first.
The actual observed maximum position is1. Quote refresh and full executable-
equity accounting reuse the reviewed maker mechanics.

100ms is an event sampling throttle, not a fixed time grid or time-weighted
average. On a busy tape100 samples cover roughly10 seconds, whereas100 events
can represent a much shorter, variable horizon. Gaps do not invent observations.

| Same full V2 tape | PnL | Sampled drawdown | Max abs inventory |
|---|---:|---:|---:|
| Reconstructed100-event baseline | 322 | 5 | 2 |
| Selected thinned/reduce-first window | 1815 | 3 | 1 |
| Established maker, cap1 control | **1938** | **2** | **1** |
| Established maker, unchanged cap2 | 1992 | 2 | 2 |

Thus the two changes improve this particular reconstructed baseline, but do not
establish that the rolling-mean signal adds value beyond simpler inventory
management. The cap1 control beats the selected window on PnL and sampled
drawdown at the same observed maximum position. Keep the existing V2 maker as
the preferred tested artifact; do not promote the window simply because it is
more elaborate. No claim of beating the friend's real strategy is justified.

Selected window:3455 filled orders/volume, cash11819, final inventory-1, official
mark10004, PnL1815; no penalty. Final interval after3800s adds598. The full tape
has already been examined during earlier research, so these are reused public
comparisons, not untouched holdouts or independent profitability estimates.
The selected file's defaults were frozen before these window full runs.

Passive fills can still be adverse: buying at the bid does not help if the bid
keeps falling. There is no post-only API; a quote can become marketable during
5ms activation delay. Inventory caps and loss triggers do not guarantee a money
loss bound when liquidity vanishes. The existing incomplete-mark and gap risks
remain. Posting one order simplifies risk tracking but reduces available quotes.

The local screen now explicitly allows standard-library `collections.deque`.
Server static acceptance remains untested. Four new tests cover sum/eviction,
event vs throttled sampling, missing books, and pending-cancel/partial-fill
reservation. Run the complete suite and screen:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m scripts.check_playground_submission strategies/window_maker.py
.venv/bin/python -m simulator.main --strategy strategies/window_maker.py --backtest data/sample_v2.csv --log-dir logs/window/check --no-logs
```

JSON records retain parameter overrides, source/data hashes and exact metrics.
For event baseline reproduction, use the experiment harness with
`SAMPLE_US=0, REDUCE_FIRST=False`; the selected standalone defaults are
`SAMPLE_US=100000, REDUCE_FIRST=True`. No push or submission was performed.
