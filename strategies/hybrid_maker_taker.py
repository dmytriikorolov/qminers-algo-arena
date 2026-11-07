"""Capacity inventory cycling plus selective, price-bounded fair-value IOC orders."""
from __future__ import annotations

from collections import deque

from simulator.models import OrderBookSnapshot, OrderRequest, OrderStatus, OrderType, PrivateOrderEvent, Side, Trade
from simulator.strategy import BaseStrategy


class HybridMakerTakerStrategy(BaseStrategy):
    """One live/pending order; cancel confirmation precedes any replacement.

    Fair value is a rolling market-owned midpoint mean including the current
    observation. It is an estimate, not guaranteed executable profit. IOC
    prices never sweep past the observed touch: latency may cause a miss,
    but cannot cause a worse fill than the submitted limit. The two price
    units of default edge are a conservative hurdle, not a fee estimate.

    Diagnostics are memory-bounded; the comparison runner drains them after
    every callback to JSONL. Standalone runs expose dropped_diagnostics.
    """

    def __init__(self, exposure_limit: int = 100, max_order_size: int = 200,
                 fair_value_window: int = 100, taker_threshold: float = 2.0):
        super().__init__()
        if exposure_limit < 1 or max_order_size < 1 or fair_value_window < 1 or taker_threshold < 0:
            raise ValueError('Positive limits/window and nonnegative threshold required')
        self._limit = exposure_limit
        self._max_order_size = max_order_size
        self._threshold = taker_threshold
        self._window: deque[float] = deque(maxlen=fair_value_window)
        self._inventory = 0
        self._order_id: str | None = None
        self._side: Side | None = None
        self._price: int | None = None
        self._remaining = 0
        self._accepted = False
        self._cancel_pending = False
        self._mode: str | None = None
        self.diagnostics: deque[dict] = deque(maxlen=10000)
        self.dropped_diagnostics = 0

    def _record(self, data: dict) -> None:
        if len(self.diagnostics) == self.diagnostics.maxlen:
            self.dropped_diagnostics += 1
        self.diagnostics.append(data)

    def _cancel(self) -> None:
        if self._order_id is not None and self._accepted and not self._cancel_pending:
            self._cancel_pending = True
            self.cancel_order(self._order_id)

    def on_order_book_change(self, snapshot: OrderBookSnapshot, trades: list[Trade]) -> None:
        bid = next((o.price for o in snapshot.bids if o.owner == 'market'), None)
        ask = next((o.price for o in snapshot.asks if o.owner == 'market'), None)
        if bid is None or ask is None or bid <= 0 or ask <= 0 or bid >= ask:
            self._cancel()
            return
        self._window.append((bid + ask) / 2)
        fair = sum(self._window) / len(self._window)
        buy_edge, sell_edge = fair - ask, bid - fair
        side = Side.BUY if self._inventory <= 0 else Side.SELL
        price = bid if side == Side.BUY else ask
        mode, liquidity = 'maker', self._max_order_size
        if len(self._window) == self._window.maxlen:
            # No fees in this engine. Threshold also buffers fair-value error.
            buy_capacity = self._limit - self._inventory
            sell_capacity = self._limit + self._inventory
            if buy_edge > self._threshold and buy_capacity > 0:
                side, price, mode = Side.BUY, ask, 'taker'
                liquidity = sum(o.quantity for o in snapshot.asks if o.owner == 'market' and o.price == ask)
            elif sell_edge > self._threshold and sell_capacity > 0:
                side, price, mode = Side.SELL, bid, 'taker'
                liquidity = sum(o.quantity for o in snapshot.bids if o.owner == 'market' and o.price == bid)
        sign = 1 if side == Side.BUY else -1
        capacity = self._limit - sign * self._inventory
        quantity = min(self._max_order_size, capacity, liquidity)
        if self._order_id is not None:
            if self._cancel_pending or not self._accepted or self._mode == 'taker':
                return
            improved = price > self._price if side == Side.BUY else price < self._price
            if (mode == 'maker' and self._side == side and self._remaining <= capacity
                    and not improved):
                return
            if mode == 'taker':
                self._record(dict(kind='taker_waiting_cancel', timestamp_us=snapshot.timestamp_us,
                    order_id=self._order_id, bid=bid, ask=ask, fair_value=fair,
                    buy_edge=buy_edge, sell_edge=sell_edge, side=side.value, quantity=quantity))
            self._cancel()
            return
        if quantity <= 0:
            return
        order_id = self.send_order(OrderRequest(side=side, price=price, quantity=quantity,
            order_type=OrderType.IOC if mode == 'taker' else OrderType.LIMIT))
        self._order_id, self._side, self._price = order_id, side, price
        self._remaining, self._accepted, self._mode = quantity, False, mode
        if mode == 'taker':
            self._record(dict(kind='taker_submitted', timestamp_us=snapshot.timestamp_us,
                order_id=order_id, bid=bid, ask=ask, fair_value=fair, buy_edge=buy_edge,
                sell_edge=sell_edge, side=side.value, quantity=quantity, limit_price=price))

    def on_private_order_update(self, event: PrivateOrderEvent) -> None:
        if event.order_id != self._order_id:
            return
        if self._mode == 'taker':
            self._record(dict(kind='taker_execution', timestamp_us=event.timestamp_us,
                order_id=event.order_id, status=event.status.value, filled_quantity=event.filled_quantity,
                remaining_quantity=event.remaining_quantity, fill_price=event.fill_price, message=event.message))
        if event.status == OrderStatus.ACCEPTED:
            self._accepted = True
        elif event.status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            if event.remaining_quantity < 0 or event.remaining_quantity > self._remaining:
                return
            # Engine filled_quantity is per match; remaining watermark avoids
            # duplicate accounting and handles reversed nonterminal fill reports.
            filled = self._remaining - event.remaining_quantity
            self._remaining = event.remaining_quantity
            self._inventory += filled if self._side == Side.BUY else -filled
            self._accepted = True
            if event.status == OrderStatus.FILLED and self._remaining == 0:
                self._clear()
        elif event.status == OrderStatus.CANCELED:
            self._clear()
        elif event.status == OrderStatus.REJECTED:
            if event.message and event.message.startswith('cancel rejected:'):
                self._cancel_pending = False
            else:
                self._clear()

    def _clear(self) -> None:
        self._order_id, self._side, self._price, self._mode = None, None, None, None
        self._remaining, self._accepted, self._cancel_pending = 0, False, False
