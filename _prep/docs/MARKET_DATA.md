# Analyze actual CSV observations

`arena.market_data.analyze_csv(path, kind, window=20, tick=0.1)` validates an
explicit schema and computes causal features using only rows already read.
It does not infer a strategy's fills or reconstruct order-level events.

Supported schemas, with exact column names:

| Kind | Required columns | Optional columns |
|---|---|---|
| `snapshots` | `time,bid,ask,bid_size,ask_size` | None |
| `bars` | `time,open,high,low,close,volume` | None |
| `trades` | `time,price,quantity` | `side` containing `buy`, `sell` or blank |

Times are finite nonnegative numeric values in caller-defined units, strictly
increasing. Convert source timestamps explicitly before analysis. If trades
share a timestamp, obtain a real ordering/sequence from the source; the tool
rejects duplicates instead of inventing one. Missing, nonfinite or malformed
numeric values are rejected. Extra columns are rejected to catch schema errors.

Snapshots produce midprice, spread/ticks/bps, imbalance, microprice and rolling
features. A locked book is counted; a crossed or empty book is rejected. The
configured tick converts spread units; the tool does not infer tick rules or
claim that every historical/adjusted price lies on that grid.

Bars require positive OHLC prices, `low <= open, close <= high` and nonnegative
volume. Features include close-to-close log return, range, rolling mean,
volatility, volume and close-times-volume notional. These are available only
after the current bar has completed. This notional is a close-price estimate,
not an exact volume-weighted traded amount.

Trades require positive price and quantity. Signed quantity uses only explicit
`side` values; rising prices do not cause a trade to be labelled a buy. Confirm
the source's side semantics before interpreting it as aggressor direction.
Rolling signed quantity is null if any trade in the current window has an
unknown side. Observed buy/sell totals count only explicitly labelled trades.

Analysis is bounded to 20 MiB, 100,000 rows and a window of 10,000 observations.
All rows are validated; exceeding a cap raises an error rather than reporting
partial coverage as complete. Output retains the latest 200 feature rows and
streaming summaries for every numeric feature. No Parquet dependency is needed.

`depth_features(bids, asks, k=5)` accepts actual sorted `(price, quantity)` level
arrays and returns top-k depth imbalance. It rejects crossed books, duplicates
and unsorted prices. It never extrapolates missing levels from a top-of-book
snapshot. No order-flow imbalance is computed from any of these CSV schemas.

Run tests from this kit's directory:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p test_market_data.py -v
```
