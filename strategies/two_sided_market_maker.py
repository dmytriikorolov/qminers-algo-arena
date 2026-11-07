"""Independent passive bid/ask quotes with worst-case same-side reservations."""
from __future__ import annotations

from dataclasses import dataclass

from simulator.models import (
    OrderBookSnapshot, OrderRequest, OrderStatus, OrderType,
    PrivateOrderEvent, Side, Trade,
)
from simulator.strategy import BaseStrategy


@dataclass(slots=True)
class _Quote:
    order_id: str
    side: Side
    price: int
    remaining: int
    accepted: bool = False
    cancel_pending: bool = False


class TwoSidedMarketMakerStrategy(BaseStrategy):
    """One live/pending order per side; orders remain reserved until terminal.

    Safety invariant: I + outstanding buys <= L and I - outstanding sells >= -L.
    Opposite orders are never netted when calculating capacity. Any subset or
    ordering of fills is therefore safe, including fills during cancellation.
    Quotes retain priority unless external touch improves, they cross the new
    opposite touch, data becomes invalid, or a safety check fails.

    Engine callbacks are ordered, per-match and synchronous at activation,
    after send_order returns its ID. Remaining quantities make repeated fill
    reports idempotent. Arbitrary lost/reordered terminal reports cannot be
    reconciled without an exchange order-query API, which this simulator lacks.
    """

    def __init__(self, exposure_limit: int = 100, max_order_size: int = 200):
        super().__init__()
        if exposure_limit < 1 or max_order_size < 1:
            raise ValueError('Limits must be positive')
        self._limit = exposure_limit
        self._max_order_size = max_order_size
        self._inventory = 0
        self.max_abs_inventory = 0
        self._quotes: dict[Side, _Quote] = {}
        self._orders: dict[str, _Quote] = {}

    def outstanding_quantity(self, side: Side) -> int:
        return sum(order.remaining for order in self._orders.values() if order.side == side)

    def _capacity(self, side: Side) -> int:
        sign = 1 if side == Side.BUY else -1
        return max(0, self._limit - sign * self._inventory - self.outstanding_quantity(side))

    def _cancel(self, quote: _Quote) -> None:
        # Wait for acceptance: the ID may still represent a pending submission.
        if quote.accepted and not quote.cancel_pending:
            quote.cancel_pending = True
            self.cancel_order(quote.order_id)

    def on_order_book_change(self, snapshot: OrderBookSnapshot, trades: list[Trade]) -> None:
        bid = next((order.price for order in snapshot.bids if order.owner == 'market'), None)
        ask = next((order.price for order in snapshot.asks if order.owner == 'market'), None)
        if bid is None or ask is None or bid <= 0 or ask <= 0 or bid >= ask:
            for quote in list(self._quotes.values()):
                self._cancel(quote)
            return
        for side, touch in ((Side.BUY, bid), (Side.SELL, ask)):
            quote = self._quotes.get(side)
            if quote is not None:
                sign = 1 if side == Side.BUY else -1
                unsafe = sign * self._inventory + self.outstanding_quantity(side) > self._limit
                improved = touch > quote.price if side == Side.BUY else touch < quote.price
                crosses = quote.price >= ask if side == Side.BUY else quote.price <= bid
                if unsafe or improved or crosses:
                    self._cancel(quote)
                continue
            quantity = min(self._max_order_size, self._capacity(side))
            if quantity <= 0:
                continue
            order_id = self.send_order(OrderRequest(
                side=side, price=touch, quantity=quantity, order_type=OrderType.LIMIT,
            ))
            quote = _Quote(order_id, side, touch, quantity)
            self._quotes[side] = quote
            self._orders[order_id] = quote

    def on_private_order_update(self, event: PrivateOrderEvent) -> None:
        quote = self._orders.get(event.order_id)
        if quote is None:
            return  # Duplicate terminal or late response cannot touch a replacement.
        if event.status == OrderStatus.ACCEPTED:
            quote.accepted = True
            # Never restore remaining quantity from a late ACCEPTED report.
            return
        if event.status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            remaining = event.remaining_quantity
            if remaining < 0 or remaining > quote.remaining:
                return  # Stale fill cannot increase reservations or inventory.
            filled = quote.remaining - remaining
            # filled_quantity is incremental in the engine. The remaining
            # watermark avoids double counts and reconciles reversed fill reports.
            quote.remaining = remaining
            quote.accepted = True
            self._inventory += filled if quote.side == Side.BUY else -filled
            self.max_abs_inventory = max(self.max_abs_inventory, abs(self._inventory))
            if event.status != OrderStatus.FILLED or remaining != 0:
                return
        elif event.status == OrderStatus.REJECTED:
            if event.message and event.message.startswith('cancel rejected:'):
                quote.cancel_pending = False
                return  # A rejected cancel is NOT confirmation that exposure vanished.
        elif event.status != OrderStatus.CANCELED:
            return
        self._orders.pop(event.order_id, None)
        if self._quotes.get(quote.side) is quote:
            self._quotes.pop(quote.side)
