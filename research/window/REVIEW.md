# Independent rolling-window review

The implementation is a reasonable experiment based on the user's description,
not a reproduction of the unavailable friend's exact strategy. No blocking
order-state defect was found. The selected window strategy does **not** improve
on the existing maker in the observed V2 comparison.

| Full V2 policy | PnL | Sampled drawdown | Maximum inventory |
|---|---:|---:|---:|
| Event window baseline | 322 | 5 | 2 |
| Selected thinned window, reduce first | 1815 | 3 | 1 |
| Established maker, cap 1 control | 1938 | 2 | 1 |
| Established maker, cap 2 | 1992 | 2 | 2 |

The cap 1 control earns more with lower sampled drawdown at the same observed
maximum exposure. The thinned-window improvement over the event baseline cannot
be credited entirely to its signal: sampling changes the lookback horizon and
reduce-first changes inventory behavior. No promotion over the established
maker is supported by these results.

An independent official CLI exactly reproduces the selected strategy's PnL
1815, cash 11819, inventory -1, liquidation mark 10004, 3455 fills/volume and zero
breach penalty. Source/data hashes match `selected_full.json`. Independent PnL
samples confirm maximum sampled drawdown 3, mark 1217 at 3800 seconds and
post-3800 increment 598. The latter interval is about 1950 seconds, not 20
minutes. After review, the records use explicit `elapsed_split_s`,
`pnl_at_elapsed_split` and `pnl_after_elapsed_split` names to avoid confusing
the generic harness labels with development data or a 20-minute interval.

Four new tests verify rolling sum/window eviction, event versus throttled
sampling, no invented samples over gaps, missing-side behavior, and one global
reservation through a pending cancel and a partial fill. The race test checks
capacity at every private/public callback and reconciles cash/inventory against
the official engine. A fresh complete run passes all **27 tests**.

`SAMPLE_US=100000` takes the first valid callback at least 100 ms after the last
sample. This is event throttling, not an exact time grid or a time-weighted
average. A full 100-point window approximates 10 seconds only on a busy tape;
quiet gaps extend its horizon. Event sampling counts repeated valid snapshots,
including unchanged prices and equal timestamps. Missing sides add no sample.

The single `orders` reservation correctly blocks a replacement until the prior
request terminates, including during cancel latency. Existing risks remain:
passive quotes can be selected adversely, cancellation can lose a fill race,
and incomplete liquidation depth can prevent risk marking. A drawdown trigger
is not a guaranteed loss bound. The full V2 tape was already examined before
this experiment; later results are reused public validation, not a fresh
holdout or proof of a general edge.

Reproduce from the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m simulator.main --strategy strategies/window_maker.py --backtest data/sample_v2.csv --log-dir logs/window/reviewer_selected --no-logs
```
