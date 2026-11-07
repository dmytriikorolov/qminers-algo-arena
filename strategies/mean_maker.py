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
    - a resting order is replaced when its side or market touch changes;
      unchanged quotes retain their queue priority.

    Quotes aim to capture the spread; latency can still cause taker fills.
    One order lifecycle runs at a time (sends and cancels take effect 5 ms late, and a cancel can lose the
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
        self._submit_pending = False
        self._cancel_pending_id: str | None = None
        self._order_sides: dict[str, Side] = {}
        self._resting_id: str | None = None
        self._resting_side: Side | None = None
        self._resting_price: int | None = None

    def on_order_book_change(self, snapshot: OrderBookSnapshot, trades: list[Trade]) -> None:
        """Update the mid-price window and keep one passive quote at the touch."""
        bid = next((order.price for order in snapshot.bids if order.owner == 'market'), None)
        ask = next((order.price for order in snapshot.asks if order.owner == 'market'), None)
        if bid is None or ask is None or bid >= ask:
            if self._resting_id is not None and not self._submit_pending and self._cancel_pending_id is None:
                self._cancel_pending_id = self._resting_id
                self.cancel_order(self._resting_id)
            return

        mid = (bid + ask) / 2
        self._window.append(mid)
        if len(self._window) < self._window.maxlen or self._submit_pending or self._cancel_pending_id is not None:
            return

        mean = sum(self._window) / len(self._window)
        deviation = mid - mean
        if deviation > self._deadband:
            side: Side | None = Side.SELL
        elif deviation < -self._deadband:
            side = Side.BUY
        else:
            side = Side.BUY if self._inventory <= 0 else Side.SELL

        touch = bid if side == Side.BUY else ask
        if self._resting_id is not None:
            if self._resting_side == side and self._resting_price == touch:
                return
            # Manage the existing residual before checking a replacement's size.
            self._cancel_pending_id = self._resting_id
            self.cancel_order(self._resting_id)
            return

        signed = self._quantity if side == Side.BUY else -self._quantity
        if abs(self._inventory + signed) > self._exposure_limit:
            return

        self._submit_pending = True
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
        # A fill can beat a cancel. Keep the cancel pending until its own
        # response arrives, even when the filled order has already been cleared.
        if event.order_id == self._cancel_pending_id and event.status in (
            OrderStatus.CANCELED, OrderStatus.REJECTED,
        ):
            self._cancel_pending_id = None
        side = self._order_sides.get(event.order_id)
        if side is None:
            return  # Late responses for old orders cannot clear a newer order.
        if event.status == OrderStatus.ACCEPTED:
            self._submit_pending = False
        if event.status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            self._submit_pending = False
            self._inventory += event.filled_quantity if side == Side.BUY else -event.filled_quantity

        if event.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED):
            self._order_sides.pop(event.order_id, None)
            if self._resting_id == event.order_id:
                self._submit_pending = False
                self._resting_id, self._resting_side, self._resting_price = None, None, None
