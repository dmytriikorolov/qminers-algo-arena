# V2 maker freeze

Input: data/sample_v2.csv, SHA256
dd4e00e281abe50c9a19e16c147ccbc0b5b69835fee567f00136402ef1e01d08.
2,000,000 rows from 0.027441s to 5749.896405s, insert prices 9963..10026.
The file's generator/recorded provenance is unknown; do not call it independent
recorded market evidence without organizer confirmation.

Development: original stream through 1800s, preserving all initial book orders.
Existing quotes LOT2/cap10: +809, sampled drawdown4, max inventory3.
Existing quotes LOT1/cap2/signal0/skew0.5: +620, drawdown2, max inventory2.
Correct flow LOT2/cap2: -8875. Defensive full replay reproduces the user's -30.
The friend's -200k strategy is not present and was not reproduced.

Freeze BEFORE later-data evaluation: strategies/v2_inventory_maker.py.
LOT1/cap2, signal0, skew0.5, volatility widening1, max spread6, quote age1s,
drawdown trigger20 and exit retry100ms. No parameter search after this freeze.
It is the size-limited quoting control with cash accounting and an independent
cancel-all/liquidation halt. Development result exactly +620 (no halt).

Validation: continuous replay through3800s; incremental PnL after1800s.
Final check: full replay; incremental PnL after3800s. No reset at split boundaries.
Final block will be evaluated once after the validation result. Initial public
development and the user's full defensive result were already observed, so this
is a frozen maker check within one public tape, not wholly independent research.
Prefix EOF activates pending requests; compare split marks to full replay.
No test can guarantee a20-unit loss bound across delayed cancels or missing bids.
