# Frozen Playground selection

Selected before running the full-size candidate on the last 20 minutes: flow LOT=20,
LIMIT=20, MAX_SPREAD=4; no other signal or exit changes. Development data is the
original event stream through 2400 seconds; prefix EOF drains pending orders, as
the official simulator always does. Full replay will carry all positions/order
state continuously through the split. Prefix EOF and continuous split marks can
differ if an order is pending at the boundary; report the difference if present.

Predeclared sweep: flow lots 1/5/10/20, quotes default/no-signal/no-vol/cap5,
untouched official example and no-op. Maximum flow lot 20 is the best development
PnL (16,435), with positive first and second 20-minute blocks (7,951 / 8,484),
maximum absolute inventory 20, no penalty, and sampled max drawdown 554.
LOT=10 has the same observed maximum exposure and drawdown, with lower PnL 11,187.
This is synthetic-sample sizing evidence, not an independent alpha discovery.

No holdout parameter changes are planned. A failing holdout will be reported,
not used to launch another tuning round. Candidate file:
`strategies/playground_flow.py`. Local static screening and adversarial review
must finish before recommending that file.
