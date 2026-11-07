"""Two-sided passive maker, full capacity: bid 100-I / ask 100+I at the market touch, mean-reversion gated.

v2 (2026-11-07). v1 quoted a fixed 100 lots per side from one order slot
and dropped any side where one fill could breach the limit, so most of the
time it quoted one side only (+223k on round1). v2 runs on the
`full_two_sided` engine:

- size = the room left to the limit (bid LIMIT - I, ask LIMIT + I), topped
  up with new orders as fills land, so both sides always rest at full size;
- the touch is the best *market* price (own orders excluded); an order
  that is no longer at its target is cancelled and re-joined;
- the mean-reversion signal is kept: beyond DEVIATION_DEADBAND the side
  that would chase the move (bid when the mid is rich, ask when cheap) is
  moved GATE_OFFSET ticks deeper (None = pulled). With ADDING_ONLY that
  applies only while the side would grow |inventory|.

Penalty safety: resting + in-flight quantity per side never exceeds the room
to the limit, and orders count until terminal (cancels can lose the race).
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

WINDOW_SIZE = 100  # k: how many recent mid prices the mean is taken over
DEVIATION_DEADBAND = 1  # ticks: |mid - mean| beyond this gates the move-chasing side
LIMIT = 100  # arena rule: |inventory| > 100 accrues penalty
GATE_OFFSET = 1  # ticks behind the touch for a gated side (None = no quote)
ADDING_ONLY = True  # gate a side only while it would grow |inventory|


def market_best(orders: list) -> tuple[int | None, int]:
    """Best price and total quantity there, counting market orders only."""
    price = None
    quantity = 0
    for order in orders:
        if order.owner != 'market':
            continue
        if price is None:
            price = order.price
        elif order.price != price:
            break
        quantity += order.quantity
    return price, quantity


class TwoSidedMakerStrategy(BaseStrategy):
    """Full-capacity two-sided maker with the mean-reversion gate."""

    def __init__(
        self,
        window_size: int = WINDOW_SIZE,
        deviation_deadband: float = DEVIATION_DEADBAND,
        limit: int = LIMIT,
        gate_offset: int | None = GATE_OFFSET,
        adding_only: bool = ADDING_ONLY,
    ) -> None:
        super().__init__()
        self._window: deque[float] = deque(maxlen=window_size)
        self._deadband = deviation_deadband
        self._limit = limit
        self._offset = gate_offset
        self._adding_only = adding_only
        self._inventory = 0
        # order_id -> [side, price, remaining quantity, cancel sent]
        self._orders: dict[str, list] = {}

    def on_order_book_change(self, snapshot: OrderBookSnapshot, trades: list[Trade]) -> None:
        """Update the mean, then re-join the market touch on each side and top up free capacity."""
        bid_px, _ = market_best(snapshot.bids)
        ask_px, _ = market_best(snapshot.asks)
        if bid_px is None or ask_px is None:
            return
        mid = (bid_px + ask_px) / 2
        self._window.append(mid)
        deviation = mid - sum(self._window) / len(self._window)

        targets: dict[Side, int | None] = {Side.BUY: bid_px, Side.SELL: ask_px}
        if len(self._window) == self._window.maxlen:
            if deviation > self._deadband and not (self._adding_only and self._inventory < 0):
                targets[Side.BUY] = None if self._offset is None else bid_px - self._offset
            if deviation < -self._deadband and not (self._adding_only and self._inventory > 0):
                targets[Side.SELL] = None if self._offset is None else ask_px + self._offset
        self._quote(targets)

    def _quote(self, targets: dict[Side, int | None]) -> None:
        for side, target in targets.items():
            for order_id, order in self._orders.items():
                if order[0] == side and not order[3] and order[1] != target:
                    self.cancel_order(order_id)
                    order[3] = True
            if target is None:
                continue
            room = self._limit - self._inventory if side == Side.BUY else self._limit + self._inventory
            free = room - sum(order[2] for order in self._orders.values() if order[0] == side)
            if free > 0:
                order_id = self.send_order(
                    OrderRequest(side=side, price=target, quantity=free, order_type=OrderType.LIMIT)
                )
                self._orders[order_id] = [side, target, free, False]

    def on_private_order_update(self, event: PrivateOrderEvent) -> None:
        """Track inventory and remaining quantities; drop terminal orders."""
        order = self._orders.get(event.order_id)
        if order is None:
            return
        if event.status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            self._inventory += event.filled_quantity if order[0] == Side.BUY else -event.filled_quantity
            order[2] = event.remaining_quantity
        if event.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED):
            del self._orders[event.order_id]
