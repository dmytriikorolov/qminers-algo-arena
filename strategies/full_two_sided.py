"""Full-capacity two-sided maker: bid 100-I and ask 100+I always resting at the market touch.

Measured on round1 (fill forensics + sweeps, 2026-11-07):

- Every lot a passive maker trades earns positive edge (~0.16-0.19/lot), so
  PnL is driven by volume. Quoting both sides at the full penalty-safe size
  at all times (bid = LIMIT - I, ask = LIMIT + I, topped up as fills land)
  trades ~2.5M lots vs ~1.9M for the one-sided inventory cycle.
- The touch is the best *market* price (`owner == 'market'`): the snapshot
  includes our own orders, and fills while we sit alone ahead of the market
  marked out at -0.4..-0.7/lot.
- Top-of-book imbalance (bid_qty - ask_qty)/(bid_qty + ask_qty) predicts
  the mid +-0.34 ticks over 250 events. Fills whose own side is thin mark
  out negative. Gating both sides on it costs too much volume, but gating
  only the side that GROWS |inventory| keeps the cycle running and lifts
  per-lot edge: +458k vs +426k ungated (plateau 445-458k for gate -0.5..-0.9).

Penalty safety: resting + in-flight quantity per side never exceeds the room
left to the limit, and orders count until their terminal event (a cancel can
lose the race against a fill), so no combination of fills can push |I| past
LIMIT.
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

LIMIT = 100  # arena rule: |inventory| > 100 accrues penalty
IMB_GATE = -0.8  # own-side top-of-book imbalance below this -> the |I|-growing side quotes deeper
GATE_OFFSET = 1  # ticks behind the touch for a gated side


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


class FullTwoSidedStrategy(BaseStrategy):
    """Keep the whole penalty-safe size quoted on both sides at the market touch."""

    def __init__(self, limit: int = LIMIT, imb_gate: float | None = IMB_GATE, gate_offset: int = GATE_OFFSET) -> None:
        super().__init__()
        self._limit = limit
        self._gate = imb_gate
        self._offset = gate_offset
        self._inventory = 0
        # order_id -> [side, price, remaining quantity, cancel sent]
        self._orders: dict[str, list] = {}

    def _committed(self, side: Side) -> int:
        return sum(order[2] for order in self._orders.values() if order[0] == side)

    def on_order_book_change(self, snapshot: OrderBookSnapshot, trades: list[Trade]) -> None:
        """Re-join the market touch on each side and top up any free capacity."""
        bid_px, bid_qty = market_best(snapshot.bids)
        ask_px, ask_qty = market_best(snapshot.asks)
        if bid_px is None or ask_px is None:
            return

        bid_target, ask_target = bid_px, ask_px
        if self._gate is not None:
            imbalance = (bid_qty - ask_qty) / (bid_qty + ask_qty)
            # Only the side that would grow |inventory| is gated; the reducing
            # side always stays at the touch so the cycle keeps turning.
            if imbalance < self._gate and self._inventory >= 0:
                bid_target = bid_px - self._offset
            if -imbalance < self._gate and self._inventory <= 0:
                ask_target = ask_px + self._offset

        for side, target in ((Side.BUY, bid_target), (Side.SELL, ask_target)):
            for order_id, order in self._orders.items():
                if order[0] == side and not order[3] and order[1] != target:
                    self.cancel_order(order_id)
                    order[3] = True
            room = self._limit - self._inventory if side == Side.BUY else self._limit + self._inventory
            free = room - self._committed(side)
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
