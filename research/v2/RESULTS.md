# Changed-data experiment and defensive-flow exploit

## Skill and approach

Applied the existing systematic-debugging and verification-before-completion
skills, plus an independent reviewer agent. No dedicated trading-adversary skill
is installed or required. The official exchange remains unchanged; no memory
tool, dependency, network service or external trading code was added.

## Input and reproduced failure

`data/sample_v2.csv`:2,000,000 events, first timestamp0.027441s, last5749.896405s,
insert price range9963..10026. SHA256:
`dd4e00e281abe50c9a19e16c147ccbc0b5b69835fee567f00136402ef1e01d08`.
1,033,029 resting inserts,34,503 IOC inserts,932,468 cancels. This is the
new local file; the old `sample.csv` is still present and unchanged. Whether the
new tape is recorded or synthetic has not been independently verified.

Official CLI reproduces defensive flow-30,18 filled orders,36 volume, flat final
inventory, no penalty. It halts at173.387931s and finishes liquidation5ms later.
Its first nine round trips yield-6,+2,0,-2,-4,-4,-4,-6,-6. Most exits are the
arbitrary five-second timeout: the strategy pays spreads without a continuation
edge on this tape. No accounting bug explains the loss. The friend's reported
-200k file is not in the repository and has not been reproduced.

The reviewer found a deterministic bait: keep bid100, trade at ask102, cancel
the ask and replace it at104. Midpoint rises by one, satisfying confirmation,
although the executable selling price never improves. Defensive flow buys2 at104
and times out selling100: loss8. Repeat the bait and it halts at-32, beyond its
nominal30 trigger. Tests compare size-matched flow(-4) and no-op(0) on the same
single-bait tape. The old strategy is preserved as evidence, not silently fixed.

## New frozen candidate

**`strategies/v2_inventory_maker.py`**, class `InventoryMakerStrategy`.

- LIMIT quotes, LOT1, position cap2. Joins or quotes behind market touch;
  never deliberately crosses on normal entry. A delayed quote can become
  marketable during the5ms send latency; passive execution is not guaranteed.
- Center = market midpoint minus0.5 ticks per inventory unit. Displayed
  microprice weight is zero; no unsupported claim of predictive imbalance edge.
  Existing causal volatility widening is retained.
- At most one outstanding order per side; pending and canceling orders retain
  their remaining size until terminal private updates. Quote refresh age1s.
- Exact private-fill cash/inventory accounting. Executable visible-depth equity
  drawdown20 triggers permanent halt, cancels all quotes, waits for terminal
  updates, then sizes IOC liquidation from the actual current inventory.
- IOC exits retry after100ms if needed. No signal-based forced timeout exit.

Development first1800s tested existing quotes(+809, sampledDD4), size-limited
quote control(+620, sampledDD2), and flow2(-8875). Selected the small control
with an independent drawdown halt, then froze parameters in `SELECTION.md`
before evaluating later intervals. Retained the larger quoting result honestly;
the new candidate is chosen for smaller exposure, not maximum development PnL.

## Official-engine results

All policies see the identical event stream, public depth20,5ms action latency,
100-unit penalty threshold,1000 potential-position rejection limit and10,000/s
penalty. No fees; end inventory uses official market-book liquidation value.

| Policy | Full PnL | Maximum abs inventory | Sampled max drawdown | Penalty |
|---|---:|---:|---:|---:|
| New maker | **1992** | 2 | 2 | 0 |
| Existing defensive | -30 | 2 | 30 | 0 |
| Flow LOT2/cap2 control | -28273 | 2 | 28273 | 0 |
| No-op | 0 | 0 | 0 | 0 |

Maker increments620 /690 /682 across the development, validation and final
intervals. Validation prefix ends at3800s; continuous full replay's split mark
is also1310. Development prefix score620 also matches validation's first split.
Splits use elapsed marks relative to first event, while prefixes cut absolute
tape time; the27.441ms origin offset and EOF pending-action drain cause no PnL
discrepancy for these maker comparisons. Book/orders/inventory carry continuously;
these intervals are not separate seeded runs or independent datasets.

Full maker:2,529 filled orders/units, final inventory-1, cash11,996, liquidation
mark10,004, PnL1,992. Time-weighted abs-inventory q50/q68/q95/q99.7=0/1/1/2.
Maximum submitted reserved exposure2. Minimum send-to-fill latency5,189us.
18,230 accepted requests, 15,699 cancellation events, 31 rejected operations.
The independent full-run observer confirmed all 31 are cancels losing a fill
race, with message "cancel rejected: no resting order with this id"; none are
new-order or position-limit rejections.
No drawdown halt on V2. Local harness runtime about25s; server resource limits
have not been directly measured. JSON records retain exact source/data hashes.

Independent full official CLI reproduced the maker result. All23 integration
tests pass, including quote fills racing a halt/cancel and subsequent IOC sizing.
Local submission screening passes; actual server static acceptance is untested.

## Critical risks

This is one public tape, with limited development comparisons and a frozen later
check. It is not evidence of universal profitability. On the old synthetic
trending tape, the same maker loses20 and halts. Unknown data provenance, changing
regimes, queues, latency and available depth remain material.

The20-unit drawdown is an exit trigger, not a guaranteed maximum loss. A reviewer
test removes bids until they return much lower: maker retains its real inventory
and loses60. Incomplete visible liquidation depth prevents a full equity mark;
the strategy has no separate timeout/unknown-mark exit policy. Missing callbacks
delay actions. End-of-file marking includes residual inventory rather than
proving the strategy achieved an actual flat exit. Cancel rejections after fills
can be benign and must not clear other live risk reservations.

Next useful experiment: on new organizer data, freeze this maker and compare
small-size quote controls with/without inventory skew and volatility widening
on fresh chronological intervals. First address incomplete-mark risk with a
separate candidate and explicit missing-liquidity tests. Do not tune the current
file on the already-inspected final block or simply scale its lots to chase PnL.

## Exact commands

```bash
.venv/bin/python -m simulator.main --strategy strategies/v2_inventory_maker.py --backtest data/sample_v2.csv --log-dir logs/v2/maker-check --no-logs
.venv/bin/python -m scripts.v2_experiments --stage validation
.venv/bin/python -m scripts.v2_experiments --stage final
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m scripts.check_playground_submission strategies/v2_inventory_maker.py
```

Submit only `strategies/v2_inventory_maker.py` if approved by the team. No push,
merge or submission was performed. Existing strategies, simulator and `_prep/`
are untouched. The original Playground deadline remains12:00 Prague unless the
organizers say otherwise; no deadline extension has been assumed.
