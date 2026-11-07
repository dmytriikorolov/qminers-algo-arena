"""Fast-flip hysteresis cycler: `cycler_hysteresis20` with the flip dead window closed.

The base cycler (Dima's, +339,278 on round1) flips its preferred side only
when inventory reaches +/-FLIP_INVENTORY instead of at every zero crossing,
riding directional fill runs and keeping queue position; at each flip it
cancels the resting order, waits out the 5 ms cancel latency, and only then
quotes the new side - a dead window with no order live, right when the flow
that caused the flip is strongest.

This variant sends the new-side order immediately, together with the cancel,
sized at the current capacity. It is safe by construction: the resting order's
remaining quantity r always satisfies I + sign*r <= 100 (that is how it was
sized), so whether or not it fills during the cancel race, the new order's
own full fill lands inventory within [-100, 100] - worst case endpoint
r - 100, which never leaves the penalty-free zone. Same-side touch chases
cannot use the trick (the resting order already carries the full capacity, so
a second same-side order would have to be size zero) and keep the
cancel-then-wait flow.
"""

from __future__ import annotations

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

FLIP_INVENTORY = 70  # |inventory| that flips the preferred side
QUOTE_QUANTITY = 100  # amplitude: a full fill lands |inventory| at exactly this
FAST_FLIP = True  # send the new-side order immediately at a side flip


class CyclerFastFlipStrategy(BaseStrategy):
    """One-sided hysteresis cycler that re-quotes without a dead window at flips."""

    def __init__(
        self,
        flip_inventory: int = FLIP_INVENTORY,
        quote_quantity: int = QUOTE_QUANTITY,
        fast_flip: bool = FAST_FLIP,
    ) -> None:
        super().__init__()
        self._flip = flip_inventory
        self._quantity = quote_quantity
        self._fast_flip = fast_flip
        self._inventory = 0
        self._preferred_side: Side = Side.BUY
        self._order_sides: dict[str, Side] = {}
        self._cancel_pending: set[str] = set()
        self._resting_id: str | None = None
        self._resting_side: Side | None = None
        self._resting_price: int | None = None

    def _cancel_once(self, order_id: str) -> None:
        """Send a cancel unless one for this order is already in flight."""
        if order_id not in self._cancel_pending:
            self._cancel_pending.add(order_id)
            self.cancel_order(order_id)

    def on_order_book_change(self, snapshot: OrderBookSnapshot, trades: list[Trade]) -> None:
        """Keep one order at the touch on the preferred side; flip fast."""
        if not snapshot.bids or not snapshot.asks:
            if self._resting_id is not None:
                self._cancel_once(self._resting_id)
            return

        # Hysteresis: keep the preferred side until inventory reaches its far side.
        if self._preferred_side == Side.BUY and self._inventory >= self._flip:
            self._preferred_side = Side.SELL
        elif self._preferred_side == Side.SELL and self._inventory <= -self._flip:
            self._preferred_side = Side.BUY
        side = self._preferred_side
        sign = 1 if side == Side.BUY else -1
        capacity = self._quantity - sign * self._inventory
        if capacity <= 0:
            if self._resting_id is not None:
                self._cancel_once(self._resting_id)
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
                    return  # behind the touch, but it has not improved past us: keep the queue
                self._cancel_once(self._resting_id)
                return  # wait for CANCELED, then re-quote at the improved touch
            # Side flip: cancel the old order and send the new side at once.
            self._cancel_once(self._resting_id)
            if self._fast_flip:
                self._send(side, touch, capacity)
            return
        self._send(side, touch, capacity)

    def _send(self, side: Side, price: int, quantity: int) -> None:
        """Rest one order and remember it as the quoted order."""
        order_id = self.send_order(
            OrderRequest(
                side=side,
                price=price,
                quantity=quantity,
                order_type=OrderType.LIMIT,
            )
        )
        self._order_sides[order_id] = side
        self._resting_id, self._resting_side, self._resting_price = order_id, side, price

    def on_private_order_update(self, event: PrivateOrderEvent) -> None:
        """Accumulate inventory on fills (both transition orders count); clear on terminal."""
        if event.status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            side = self._order_sides.get(event.order_id)
            if side is not None:
                self._inventory += event.filled_quantity if side == Side.BUY else -event.filled_quantity

        if event.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED):
            self._order_sides.pop(event.order_id, None)
            self._cancel_pending.discard(event.order_id)
            if self._resting_id == event.order_id:
                self._resting_id, self._resting_side, self._resting_price = None, None, None
