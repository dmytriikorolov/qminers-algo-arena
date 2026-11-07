"""ML maker: the inventory-cycle skeleton whose quoted side is set by a Ridge model.

The model was fitted offline on the first 70% of round1 (617,478 rows, target
the signed mid move over the next 100 events) on 11 causal features a
strategy can compute online; out-of-sample on the held-out last 30% the
prediction quintiles separated -0.27 -> +0.26 ticks of actual move. It is
embedded here as standardized-Ridge constants, and the features are
recomputed online with exactly the training recursions (EWMA taker-flow at
half-lives 5/20/50/200 normalized by EWMA volume, touch imbalance, spread,
mid-momentum, deviation from the trailing 100-event mean, event rate, time
since the last trade, last-trade flow).

Measured on that held-out last 30%: the directional override loses to the
pure cycle at every band - 84,170 (0.05) / 85,801 (0.10) / 90,684 (0.15) /
95,978 (0.25) vs inventory_cycle's 95,818 (flow_maker 70,996), with traded
volume cut 16-26% because the momentum side fills only on counter-flow dips.
The prediction's quintile spread (+/-0.26 ticks over 100 events) is smaller
than the 1-tick spread harvest the cycle already earns per round trip. Same
lesson as the cycle's flow gates: max presence on the reducing side wins.
Kept as a negative result; PRED_BAND = 1e6 reduces this file bit-for-bit to
inventory_cycle (verified: identical fills, volume and PnL).

Quoting is `inventory_cycle`'s: one touch-joined order whose size lands
|inventory| at exactly 100 on the quoted side (double-size reducing), so a
full fill never breaches the penalty zone and queue priority is kept unless
the side changes or the touch improves past the resting price. The model only
chooses the side: a predicted move beyond +/-PRED_BAND ticks rides that
direction, inside the band the side is the flat-reducing side as in the pure
cycle; when the signal side is already at its exposure extreme the strategy
falls back to the reducing side rather than standing down (measured: any loss
of presence costs ~100k on a full tape).
"""

from __future__ import annotations

from math import log

from simulator.models import (
    OrderBookSnapshot,
    OrderRequest,
    OrderStatus,
    OrderType,
    PrivateOrderEvent,
    Side,
    Trade,
)
from simulator.strategy import BaseStrategy

PRED_BAND = 0.10  # ticks of predicted 100-event move needed to override the reducing side
QUOTE_QUANTITY = 100  # base amplitude: a full fill lands |inventory| at exactly this
FLOW_HALF_LIVES = (5, 20, 50, 200)  # events; EWMA half-lives of the flow num/denom pairs

# Ridge fit on the first 70% of round1; feature order:
# flow_hl5, flow_hl20, flow_hl50, flow_hl200, imbalance, spread, momentum,
# deviation, log_rate, log_dt_trade, last_flow
FEATURE_MEAN = (-0.004370, -0.002842, 0.000665, 0.003918, 0.001757, 1.070595, 0.000016, 0.000802, 8.032781, -2.725310, 0.000031)
FEATURE_STD = (0.925385, 0.806526, 0.672227, 0.458188, 0.705202, 0.259664, 0.006292, 0.275100, 0.328601, 1.333814, 0.147044)
RIDGE_COEF = (0.036112, -0.024755, 0.145377, 0.052927, 0.011705, 0.002402, 0.050335, -0.138440, -0.000253, 0.000174, 0.001338)
RIDGE_INTERCEPT = 0.001716


class MlMakerStrategy(BaseStrategy):
    """Inventory-cycling maker whose side is chosen by an embedded Ridge model."""

    def __init__(
        self,
        quote_quantity: int = QUOTE_QUANTITY,
        pred_band: float = PRED_BAND,
    ) -> None:
        super().__init__()
        self._quantity: int = quote_quantity
        self._band: float = pred_band
        # feature state, exactly as in the training recorder
        self._flow_g = [1.0 - 0.5 ** (1 / hl) for hl in FLOW_HALF_LIVES]
        self._flow_num = [0.0] * len(FLOW_HALF_LIVES)
        self._flow_den = [0.0] * len(FLOW_HALF_LIVES)
        self._mom = 0.0
        self._mom_g = 1.0 - 0.5 ** (1 / 20)
        self._rate = 1.0
        self._rate_g = 1.0 - 0.5 ** (1 / 200)
        self._win: list[float] = []
        self._win_sum = 0.0
        self._last_mid: float | None = None
        self._last_ts: int | None = None
        self._last_trade_ts: int | None = None
        # standardized Ridge folded into a single dot product
        self._w = [c / s for c, s in zip(RIDGE_COEF, FEATURE_STD)]
        self._b = RIDGE_INTERCEPT - sum(
            c * m / s for c, m, s in zip(RIDGE_COEF, FEATURE_MEAN, FEATURE_STD)
        )
        # order state, as in inventory_cycle
        self._inventory = 0
        self._order_sides: dict[str, Side] = {}
        self._resting_id: str | None = None
        self._resting_side: Side | None = None
        self._resting_price: int | None = None

    def on_order_book_change(self, snapshot: OrderBookSnapshot, trades: list[Trade]) -> None:
        """Update the features, predict, and keep one order at the touch."""
        # market orders only: matches the book the model was trained on
        bids = [o for o in snapshot.bids if o.owner == 'market']
        asks = [o for o in snapshot.asks if o.owner == 'market']
        if not bids or not asks:
            return

        # --- features: the training recorder's recursions, verbatim ---
        ts = snapshot.timestamp_us
        bid, ask = bids[0], asks[0]
        mid = (bid.price + ask.price) / 2
        dt_s = (ts - self._last_ts) * 1e-6 if self._last_ts is not None else 0.0
        self._last_ts = ts
        svol = 0.0
        tvol = 0.0
        for trade in trades:
            v = trade.quantity if trade.book_side == 'ask' else -trade.quantity
            svol += v
            tvol += v if v > 0 else -v
        if trades:
            self._last_trade_ts = ts
        for j, g in enumerate(self._flow_g):
            self._flow_num[j] += g * (svol - self._flow_num[j])
            self._flow_den[j] += g * (tvol - self._flow_den[j])
        bidq, askq = bid.quantity, ask.quantity
        imbalance = (bidq - askq) / (bidq + askq) if bidq + askq else 0.0
        dm = mid - self._last_mid if self._last_mid is not None else 0.0
        self._mom += self._mom_g * (dm - self._mom)
        self._win.append(mid)
        self._win_sum += mid
        if len(self._win) > 100:
            self._win_sum -= self._win.pop(0)
        deviation = mid - self._win_sum / len(self._win)
        self._rate += self._rate_g * ((1.0 / dt_s if dt_s > 0 else self._rate) - self._rate)
        dt_trade = (ts - self._last_trade_ts) * 1e-6 if self._last_trade_ts is not None else 1.0
        self._last_mid = mid
        feats = (
            self._flow_num[0] / self._flow_den[0] if self._flow_den[0] > 1e-9 else 0.0,
            self._flow_num[1] / self._flow_den[1] if self._flow_den[1] > 1e-9 else 0.0,
            self._flow_num[2] / self._flow_den[2] if self._flow_den[2] > 1e-9 else 0.0,
            self._flow_num[3] / self._flow_den[3] if self._flow_den[3] > 1e-9 else 0.0,
            imbalance,
            ask.price - bid.price,
            self._mom,
            deviation,
            log(self._rate if self._rate > 1e-3 else 1e-3),
            log(dt_trade + 1e-3),
            svol / tvol if tvol else 0.0,
        )
        pred = self._b + sum(w * x for w, x in zip(self._w, feats))

        # --- side and size: inventory_cycle's mechanics, model-chosen side ---
        if pred > self._band:
            side: Side = Side.BUY
            quantity = self._quantity - self._inventory  # a full fill lands exactly +100
        elif pred < -self._band:
            side = Side.SELL
            quantity = self._quantity + self._inventory  # a full fill lands exactly -100
        else:
            side = Side.BUY if self._inventory <= 0 else Side.SELL
            quantity = self._quantity + abs(self._inventory)
        if quantity <= 0:
            # the signal side is already at its extreme: keep cycling the
            # reducing side instead of standing down (presence is the edge)
            side = Side.BUY if self._inventory <= 0 else Side.SELL
            quantity = self._quantity + abs(self._inventory)

        touch = bid.price if side == Side.BUY else ask.price
        if self._resting_id is not None:
            if self._resting_side == side:
                if self._resting_price == touch:
                    return  # already quoted at the touch
                improved_past = (side == Side.BUY and touch > self._resting_price) or (
                    side == Side.SELL and touch < self._resting_price
                )
                if not improved_past:
                    return  # still at the touch, keep queue priority
            self.cancel_order(self._resting_id)
            return  # wait for the CANCELED event, then re-quote

        order_id = self.send_order(
            OrderRequest(
                side=side,
                price=touch,
                quantity=quantity,
                order_type=OrderType.LIMIT,
            )
        )
        self._order_sides[order_id] = side
        self._resting_id, self._resting_side, self._resting_price = order_id, side, touch

    def on_private_order_update(self, event: PrivateOrderEvent) -> None:
        """Accumulate inventory on fills; free the slot once the order is terminal."""
        if event.status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            side = self._order_sides.get(event.order_id)
            if side is not None:
                self._inventory += event.filled_quantity if side == Side.BUY else -event.filled_quantity

        if event.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED):
            self._order_sides.pop(event.order_id, None)
            if self._resting_id == event.order_id:
                self._resting_id, self._resting_side, self._resting_price = None, None, None
