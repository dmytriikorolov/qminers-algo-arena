"""Passive mean-reversion maker: rests a limit order at the touch, side chosen by the window mean."""

from __future__ import annotations

from collections import deque

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

WINDOW_SIZE = 100  # k: how many recent mid prices the mean is taken over
DEVIATION_DEADBAND = 1  # t in ticks: |mid - mean| beyond this overrides the flat-reduction side
QUOTE_QUANTITY = 100  # lots per resting order (a single fill must not breach the penalty zone)
EXPOSURE_LIMIT = 100  # arena rule: |inventory| > 100 accrues penalty, so |I + s*q| stays <= this


class MeanMakerStrategy(BaseStrategy):
    """Market-making variant of the mean reversion: post, don't take.

    At most one resting limit order at a time, joined to the touch:

    - when |mid - mean| exceeds the deadband, quote the mean-reversion side
      (above the mean quote the ask, below it the bid);
    - within the deadband, quote whichever side moves inventory toward flat,
      which also keeps the quote stable while the mid hovers around the mean;
    - a resting order is replaced only when the desired side changes or the
      touch improves past its price, so queue priority is kept otherwise.

    Fills earn the spread instead of paying it. One order lifecycle runs at a
    time (sends and cancels take effect 5 ms late, and a cancel can lose the
    race against a fill), and the exposure bound guarantees a single fill can
    never push |inventory| into the penalty zone.
    """

    def __init__(
        self,
        window_size: int = WINDOW_SIZE,
        deviation_deadband: int = DEVIATION_DEADBAND,
        quote_quantity: int = QUOTE_QUANTITY,
        exposure_limit: int = EXPOSURE_LIMIT,
    ) -> None:
        super().__init__()
        self._window: deque[float] = deque(maxlen=window_size)
        self._deadband: int = deviation_deadband
        self._quantity: int = quote_quantity
        self._exposure_limit: int = exposure_limit
        self._inventory: int = 0
        self._outstanding: int = 0  # orders sent but not yet terminal
        self._order_sides: dict[str, Side] = {}
        self._resting_id: str | None = None
        self._resting_side: Side | None = None
        self._resting_price: int | None = None

    def on_order_book_change(self, snapshot: OrderBookSnapshot, trades: list[Trade]) -> None:
        """Update the mid-price window and keep one passive quote at the touch."""
        if not snapshot.bids or not snapshot.asks:
            return

        mid = (snapshot.bids[0].price + snapshot.asks[0].price) / 2
        self._window.append(mid)
        if len(self._window) < self._window.maxlen or self._outstanding > 0:
            return

        mean = sum(self._window) / len(self._window)
        deviation = mid - mean
        if deviation > self._deadband:
            side: Side | None = Side.SELL
        elif deviation < -self._deadband:
            side = Side.BUY
        else:
            side = Side.BUY if self._inventory <= 0 else Side.SELL

        # A single fill must never push |inventory| into the penalty zone;
        # stand down (keeping any existing resting order) if it could.
        if side is not None:
            signed = self._quantity if side == Side.BUY else -self._quantity
            if abs(self._inventory + signed) > self._exposure_limit:
                return

        touch = snapshot.bids[0].price if side == Side.BUY else snapshot.asks[0].price
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
                quantity=self._quantity,
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
            self._outstanding = max(0, self._outstanding - 1)
            if self._resting_id == event.order_id:
                self._resting_id, self._resting_side, self._resting_price = None, None, None
