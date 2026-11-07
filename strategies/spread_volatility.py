"""Sequential passive quotes driven by spread and rolling price-change volatility.

Volatility is the sample standard deviation of the last WINDOW_RETURNS
market-event midpoint changes, in price units per event (not annualized).
Quotes widen with volatility. Flat entry requires spread >= MIN_SPREAD +
ENTRY_VOL_MULTIPLIER * volatility. Inventory-reducing quotes bypass that gate.
Latency can turn a submitted limit into a taker; passive fills are not assured.
"""

from __future__ import annotations

from collections import deque
from math import ceil, floor, sqrt

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


WINDOW_RETURNS = 100
MIN_SPREAD = 1.0
ENTRY_VOL_MULTIPLIER = 1.0
QUOTE_VOL_MULTIPLIER = 2.0
MIN_HALF_WIDTH = 0.5
QUOTE_QUANTITY = 10
EXPOSURE_LIMIT = 90
MAX_QUOTE_AGE_US = 1_000_000


class SpreadVolatilityStrategy(BaseStrategy):
    """One order at a time: bid when flat/short, ask when long.

    Keep queue priority while side and price stay unchanged. Quote quantities
    are clipped to flatten existing inventory before starting another cycle.
    Defaults are research parameters, not profitability-tested settings.
    """

    def __init__(self) -> None:
        super().__init__()
        self._returns: deque[float] = deque(maxlen=WINDOW_RETURNS)
        self._previous_mid: float | None = None
        self._previous_time: int | None = None
        self._volatility = 0.0
        self._inventory = 0
        self._submit_pending = False
        self._cancel_pending_id: str | None = None
        self._order_sides: dict[str, Side] = {}
        self._resting_id: str | None = None
        self._resting_side: Side | None = None
        self._resting_price: int | None = None

    def _cancel_quote(self) -> None:
        if self._resting_id is not None and not self._submit_pending and self._cancel_pending_id is None:
            self._cancel_pending_id = self._resting_id
            self.cancel_order(self._resting_id)

    def on_order_book_change(self, snapshot: OrderBookSnapshot, trades: list[Trade]) -> None:
        bid = next((o.price for o in snapshot.bids if o.owner == 'market'), None)
        ask = next((o.price for o in snapshot.asks if o.owner == 'market'), None)
        now = snapshot.timestamp_us
        if bid is None or ask is None or bid >= ask:
            self._previous_mid = None
            self._returns.clear()
            self._cancel_quote()
            return
        mid = (bid + ask) / 2
        if self._previous_time is not None and now - self._previous_time > MAX_QUOTE_AGE_US:
            self._returns.clear()
            self._previous_mid = None
        if self._previous_mid is not None:
            self._returns.append(mid - self._previous_mid)
        self._previous_mid, self._previous_time = mid, now
        if len(self._returns) < WINDOW_RETURNS:
            self._cancel_quote()
            return
        average = sum(self._returns) / WINDOW_RETURNS
        self._volatility = sqrt(sum((change - average)**2 for change in self._returns) / (WINDOW_RETURNS - 1))
        if self._submit_pending or self._cancel_pending_id is not None:
            return

        spread = ask - bid
        reducing = self._inventory != 0
        if not reducing and spread < MIN_SPREAD + ENTRY_VOL_MULTIPLIER * self._volatility:
            self._cancel_quote()
            return
        side = Side.BUY if self._inventory <= 0 else Side.SELL
        half_width = max(MIN_HALF_WIDTH, spread / 2, QUOTE_VOL_MULTIPLIER * self._volatility)
        # Inventory shifts both reference prices toward reducing exposure.
        center = mid - (self._inventory / EXPOSURE_LIMIT) * half_width
        price = min(bid, floor(center - half_width)) if side == Side.BUY else max(ask, ceil(center + half_width))
        if price <= 0:
            self._cancel_quote()
            return
        if self._resting_id is not None:
            if self._resting_side == side and self._resting_price == price:
                return
            self._cancel_quote()
            return
        capacity = EXPOSURE_LIMIT - self._inventory if side == Side.BUY else EXPOSURE_LIMIT + self._inventory
        quantity = min(QUOTE_QUANTITY, capacity)
        if reducing:
            quantity = min(quantity, abs(self._inventory))
        if quantity <= 0:
            return
        self._submit_pending = True
        order_id = self.send_order(OrderRequest(side=side, price=price, quantity=quantity, order_type=OrderType.LIMIT))
        self._order_sides[order_id] = side
        self._resting_id, self._resting_side, self._resting_price = order_id, side, price

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
