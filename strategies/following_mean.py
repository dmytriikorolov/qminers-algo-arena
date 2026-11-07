"""Mean reversion over a sliding window of mid prices.

Keeps the last `k` mid prices; when the current mid is above the window mean
it sells (expecting a fall back), when below it it buys. One-lot IOC orders at
the touch, one order in flight at a time.
"""

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

WINDOW_SIZE = 100  # k: how many recent mid prices the mean is taken over (swept on the sample data; 100 was best)
ORDER_QUANTITY = 1  # lots sent per signal
INVENTORY_CAP = 90  # stop adding exposure beyond this |inventory| (penalty zone starts at 100)


class FollowingMeanStrategy(BaseStrategy):
    """Sliding-window mean reversion: above the mean sell, below it buy.

    The window size `k` is a parameter: edit `WINDOW_SIZE` above (or pass a
    value when constructing for experiments; the arena itself builds the
    strategy with no arguments).
    """

    def __init__(self, window_size: int = WINDOW_SIZE) -> None:
        super().__init__()
        self._window: deque[float] = deque(maxlen=window_size)
        self._order_in_flight: bool = False
        self._inventory: int = 0
        self._order_sides: dict[str, Side] = {}

    def on_order_book_change(self, snapshot: OrderBookSnapshot, trades: list[Trade]) -> None:
        """Update the mid-price window and trade a lot when mid deviates from its mean."""
        if not snapshot.bids or not snapshot.asks:
            return

        mid = (snapshot.bids[0].price + snapshot.asks[0].price) / 2
        self._window.append(mid)

        # No signal until the window is full, and only one order in flight.
        if len(self._window) < self._window.maxlen or self._order_in_flight:
            return

        mean = sum(self._window) / len(self._window)
        if mid > mean:
            # Above the mean: sell at the touch, unless already too short.
            if self._inventory <= -INVENTORY_CAP:
                return
            side, price = Side.SELL, snapshot.bids[0].price
        elif mid < mean:
            # Below the mean: buy at the touch, unless already too long.
            if self._inventory >= INVENTORY_CAP:
                return
            side, price = Side.BUY, snapshot.asks[0].price
        else:
            return

        order_id = self.send_order(
            OrderRequest(
                side=side,
                price=price,
                quantity=ORDER_QUANTITY,
                order_type=OrderType.IOC,
            )
        )
        self._order_sides[order_id] = side
        self._order_in_flight = True

    def on_private_order_update(self, event: PrivateOrderEvent) -> None:
        """Accumulate inventory on fills; free the in-flight slot once the order is done."""
        if event.status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            side = self._order_sides.get(event.order_id)
            if side is not None:
                self._inventory += event.filled_quantity if side == Side.BUY else -event.filled_quantity

        if event.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED):
            self._order_sides.pop(event.order_id, None)
            self._order_in_flight = False
