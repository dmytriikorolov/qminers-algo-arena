"""One-sided passive inventory cycler: a minimal non-predictive control strategy.

No moving average, OFI, Hawkes or Kalman.  Quote at the touch on the
inventory-reducing side and use the available safe capacity (up to 200 lots).
Preserve the queue unless a better touch has appeared.

A separate experiment, NOT a validated improvement over MeanMaker.
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
parameter = 70
class CyclerHysteresis20Strategy(BaseStrategy):
    def __init__(self, exposure_limit: int = 100, max_order_size: int = 200):
        super().__init__()
        if exposure_limit < 1 or max_order_size < 1:
            raise ValueError("Limits must be positive")
        self._limit = exposure_limit
        self._max_order_size = max_order_size
        self._inventory = 0
        self._order_id: str | None = None
        self._side: Side | None = None
        self._price: int | None = None
        self._remaining = 0
        self._cancel_pending = False
        self._preferred_side = Side.BUY

    def _cancel(self) -> None:
        if self._order_id is not None and not self._cancel_pending:
            self.cancel_order(self._order_id)
            self._cancel_pending = True

    def on_order_book_change(
        self, snapshot: OrderBookSnapshot, trades: list[Trade]
    ) -> None:
        if not snapshot.bids or not snapshot.asks:
            self._cancel()
            return

        # Same simple inventory-balancing fallback as the original MeanMaker.
        # Hysteresis: don't flip direction just because inventory crosses zero.
        # This is an experiment; we test whether fewer flips improve execution.
        if self._preferred_side == Side.BUY and self._inventory >= parameter:
            self._preferred_side = Side.SELL
        elif self._preferred_side == Side.SELL and self._inventory <= -parameter:
            self._preferred_side = Side.BUY
        side = self._preferred_side
        sign = 1 if side == Side.BUY else -1

        # Since only one order is outstanding, a full remaining fill is safe.
        capacity = self._limit - sign * self._inventory
        quantity = min(self._max_order_size, capacity)
        if quantity <= 0:
            self._cancel()
            return

        touch = snapshot.bids[0].price if side == Side.BUY else snapshot.asks[0].price

        if self._order_id is not None:
            if self._cancel_pending:
                return
            if self._side == side and self._remaining <= quantity:
                # Keep queue priority if the touch hasn't improved past us.
                better_touch = (
                    (side == Side.BUY and touch > self._price)
                    or (side == Side.SELL and touch < self._price)
                )
                if not better_touch:
                    return
            self._cancel()
            return

        order_id = self.send_order(
            OrderRequest(
                side=side,
                price=touch,
                quantity=quantity,
                order_type=OrderType.LIMIT,
            )
        )
        self._order_id = order_id
        self._side = side
        self._price = touch
        self._remaining = quantity

    def on_private_order_update(self, event: PrivateOrderEvent) -> None:
        if event.order_id != self._order_id:
            return

        if event.status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            signed = 1 if self._side == Side.BUY else -1
            self._inventory += signed * event.filled_quantity
            self._remaining = event.remaining_quantity

        elif event.status == OrderStatus.ACCEPTED:
            self._remaining = event.remaining_quantity

        if event.status in (OrderStatus.FILLED, OrderStatus.CANCELED):
            self._clear()
        elif event.status == OrderStatus.REJECTED:
            # The simulator may reject a CANCEL request for an already-filled
            # order; it uses the same REJECTED status as order rejection.
            if event.message and event.message.startswith("cancel rejected:"):
                self._cancel_pending = False
            else:
                self._clear()

    def _clear(self) -> None:
        self._order_id = None
        self._side = None
        self._price = None
        self._remaining = 0
        self._cancel_pending = False
