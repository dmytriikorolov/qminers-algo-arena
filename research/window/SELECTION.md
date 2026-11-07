# Rolling-window experiment freeze

This implements the user's description, not the unavailable friend's exact code.
All variants use one globally outstanding IOC/LIMIT request slot, LOT1, cap2,
20-unit drawdown halt, terminal cancel reservations and the official5ms latency.
Warm-up requires100 valid market-only midpoint samples.

Four predefined cases on the first1800s of V2:
100-event window90PnL/DD4/maxI2; event window with reduce-inventory-first93/DD1/I1;
100ms-sampled window172/DD21/I2;100ms-sampled/reduce-first563/DD3/I1.
The existing two-sided maker earns620/DD2/I2 on the same prefix.

Frozen selection before full-window comparison: SAMPLE_US100000, WINDOW100,
REDUCE_FIRST True. Samples are taken on the first valid callback at least100ms
after the prior sample; this approximates a10-second horizon in a busy tape,
not a precisely time-weighted mean. No entry scaling until flat; maximum observed
position is1, with hardcap2 retained as a safety limit. This is research into
sampling and exposure control, not a proven improvement over the friend's code.

The complete V2 tape has already been examined in prior experiments; later
blocks are reused public validation, not a new holdout. Do not tune on full
results. Also compare a cap1 version of the established two-sided maker so that
lower risk from reduced exposure is not falsely credited to the new signal.
