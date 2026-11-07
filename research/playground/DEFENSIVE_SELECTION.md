# Defensive experiment freeze

User requested protection against exploitation after inspecting Playground
flow results. Original flow file remains unchanged and is no longer evidence
of general strategy quality. New `strategies/defensive_flow.py` is an experiment,
not a claim of a profitable real-market solution.

Parameters fixed before stress evaluation: entry LOT2 / cap5 (flat-only entries
make actual entry exposure at most2), max spread4, price confirmation after100ms
and >=1 tick in flow direction, signal TTL2s, max hold5s, cooldown1s, retry100ms,
trade liquidation loss trigger12, peak-to-liquidatable-equity halt30.
Thresholds are conservative hypotheses, not optimized official-market estimates.
Exits use visible executable market depth even with only one side present;
stop prices and maximum losses cannot be guaranteed after gaps or missing bids.

First sample replay took no trades. Instrumentation showed 593 armed signals
were cleared during the tape's atomic cancel/reinsert quote replacement, before
any complete updated book existed. Preserving signals across those transient
empty snapshots (while prohibiting entry until both sides exist) corrected this
mechanics issue: sample PnL730, 208 volume, flat final inventory, no penalty.
No threshold was changed after observing that result.

Stress generator defined before evaluation: 30 cycles per tape, seeds101–104,
continuation/reversal/gap/thin/depth-only cases. Compare unchanged flow20,
flow2/cap2 control, defensive and no-op on identical tapes through the official
engine. This isolates exposure reduction from extra logic. Test cases that
simply avoid entry are not sufficient: separate independent tests must force a
legitimate confirmed entry before testing stops, missing liquidity and exits.
Do not tune on the stress outputs; report failures and preserve them.
