"""Round 3: latency-aware, flow-conditioned passive market maker.

Only uses the public book/trade feed and private fills; never uses tape-only
F/G labels, future prices, or cancellations of invisible orders.

Save as strategies/round3_flow_maker.py and run with exchange-simulator.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import tanh

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


@dataclass(slots=True)
class Quote:
    order_id: str
    price: int
    remaining: int
    created_us: int
    cancel_pending: bool = False
    retry_at_us: int = 0


class Round3FlowMaker(BaseStrategy):
    """Passive quotes selected using observable short-term flow and book pressure.

    Upward taker pressure + bid-side OFI + rising mid leads to bid emphasis;
    symmetric pressure leads to ask emphasis. Inventory shifts both quotes
    away from increasing exposure. An outstanding order is never assumed
    cancelled until its private terminal update arrives (5 ms latency).
    """

    FLOW_WINDOW_US = 500_000
    OFI_WINDOW_US = 500_000
    MOMENTUM_WINDOW_US = 600_000
    SAMPLE_INTERVAL_US = 25_000
    QUOTE_LIFE_US = 200_000
    MIN_UPDATE_US = 40_000
    QUANTITY = 30
    INVENTORY_LIMIT = 90  # scoring penalty starts outside +/-100
    INVENTORY_SOFT = 60
    MAX_SPREAD = 12
    STRONG_SIGNAL = 0.85

    def __init__(self) -> None:
        super().__init__()
        self.inventory = 0
        self.cash = 0
        self._quotes: dict[Side, Quote] = {}
        self._flows: deque[tuple[int, int, int]] = deque()
        self._flow_count = 0
        self._flow_volume = 0
        self._ofi_events: deque[tuple[int, float]] = deque()
        self._ofi_sum = 0.0
        self._previous_touch: tuple[int, int, int, int] | None = None
        self._midpoints: deque[tuple[int, float]] = deque()
        self._last_sample_us = -10**15
        self._last_submit_us: dict[Side, int] = {
            Side.BUY: -10**15,
            Side.SELL: -10**15,
        }
        self._started_us: int | None = None

    @staticmethod
    def _market_touch(orders) -> tuple[int, int] | None:
        """Best market-owned price and aggregate depth; ignore own orders."""
        best = None
        depth = 0
        for order in orders:
            if order.owner != 'market':
                continue
            if best is None:
                best = order.price
            if order.price != best:
                break
            depth += order.quantity
        return None if best is None else (best, depth)

    @staticmethod
    def _ofi_increment(old: tuple[int, int, int, int],
                       new: tuple[int, int, int, int]) -> float:
        old_bid, old_bq, old_ask, old_aq = old
        bid, bq, ask, aq = new
        return float(
            (bq if bid >= old_bid else 0)
            - (old_bq if bid <= old_bid else 0)
            - (aq if ask <= old_ask else 0)
            + (old_aq if ask >= old_ask else 0)
        )

    def _update_signals(self, now: int, book: tuple[int, int, int, int],
                        trades: list[Trade]) -> float:
        if self._started_us is None:
            self._started_us = now

        # One count per market taker, even if its single IOC matches multiple
        # makers. Its executed volume is counted across all resulting fills.
        seen_takers: set[str] = set()
        count = 0
        volume = 0
        for t in trades:
            if t.taker_owner != 'market':
                continue
            sign = 1 if t.book_side == 'ask' else -1
            volume += sign * t.quantity
            if t.taker_order_id not in seen_takers:
                count += sign
                seen_takers.add(t.taker_order_id)
        if count or volume:
            self._flows.append((now, count, volume))
            self._flow_count += count
            self._flow_volume += volume
        cutoff = now - self.FLOW_WINDOW_US
        while self._flows and self._flows[0][0] < cutoff:
            _, expired_count, expired_volume = self._flows.popleft()
            self._flow_count -= expired_count
            self._flow_volume -= expired_volume

        if self._previous_touch is not None:
            change = self._ofi_increment(self._previous_touch, book)
            if change:
                self._ofi_events.append((now, change))
                self._ofi_sum += change
        self._previous_touch = book
        cutoff = now - self.OFI_WINDOW_US
        while self._ofi_events and self._ofi_events[0][0] < cutoff:
            _, expired = self._ofi_events.popleft()
            self._ofi_sum -= expired

        bid, bq, ask, aq = book
        mid = (bid + ask) / 2
        if now - self._last_sample_us >= self.SAMPLE_INTERVAL_US:
            self._midpoints.append((now, mid))
            self._last_sample_us = now
        cutoff = now - self.MOMENTUM_WINDOW_US
        while len(self._midpoints) > 1 and self._midpoints[1][0] <= cutoff:
            self._midpoints.popleft()
        momentum = mid - self._midpoints[0][1] if self._midpoints else 0.0

        depth = max(1.0, (bq + aq) / 2.0)
        ofi = self._ofi_sum / depth
        # Saturation keeps a single large trade/depth event from dominating.
        return (
            1.15 * tanh(self._flow_count / 3.0)
            + 0.40 * tanh(self._flow_volume / 200.0)
            + 0.42 * tanh(ofi / 1.5)
            + 0.52 * tanh(momentum / 3.0)
        )

    def _cancel(self, side: Side) -> None:
        quote = self._quotes.get(side)
        if quote is not None and not quote.cancel_pending:
            self.cancel_order(quote.order_id)
            quote.cancel_pending = True

    def _quote(self, side: Side, target: int | None, now: int) -> None:
        existing = self._quotes.get(side)
        if target is None:
            self._cancel(side)
            return
        if existing is not None:
            if existing.cancel_pending:
                return
            # Preserve queue priority through tiny changes in the market.
            age = now - existing.created_us
            danger = (side == Side.BUY and existing.price >= target + 3) or (
                side == Side.SELL and existing.price <= target - 3
            )
            if danger or (age >= self.QUOTE_LIFE_US and abs(existing.price - target) >= 2):
                self._cancel(side)
            return
        if now - self._last_submit_us[side] < self.MIN_UPDATE_US:
            return
        # Account for outstanding same-side quantity and late fills, not just
        # current inventory. Bound worst-case final inventory below +/-100.
        capacity = self.INVENTORY_LIMIT - (
            self.inventory if side == Side.BUY else -self.inventory
        )
        quantity = min(self.QUANTITY, capacity)
        if quantity < 3:
            return
        order_id = self.send_order(OrderRequest(
            side=side, price=target, quantity=quantity, order_type=OrderType.LIMIT
        ))
        self._quotes[side] = Quote(order_id, target, quantity, now)
        self._last_submit_us[side] = now

    def on_order_book_change(self, snapshot: OrderBookSnapshot,
                             trades: list[Trade]) -> None:
        now = snapshot.timestamp_us
        b = self._market_touch(snapshot.bids)
        a = self._market_touch(snapshot.asks)
        if b is None or a is None or b[0] >= a[0]:
            self._previous_touch = None
            self._cancel(Side.BUY)
            self._cancel(Side.SELL)
            return
        bid, bq = b
        ask, aq = a
        spread = ask - bid
        alpha = self._update_signals(now, (bid, bq, ask, aq), trades)
        if (self._started_us is None
                or now - self._started_us < self.FLOW_WINDOW_US
                or spread > self.MAX_SPREAD):
            self._cancel(Side.BUY)
            self._cancel(Side.SELL)
            return

        # Shift the reservation price by alpha and current inventory.
        skew = max(-3, min(3, round(0.8 * alpha - self.inventory / 32.0)))
        buy_price = max(1, min(ask - 1, bid + skew))
        sell_price = max(bid + 1, ask + skew)

        # When the signal is strong, avoid quoting the toxic side. At larger
        # inventories, prioritize the side that reduces exposure instead.
        allow_buy = alpha >= -self.STRONG_SIGNAL
        allow_sell = alpha <= self.STRONG_SIGNAL
        if self.inventory >= self.INVENTORY_SOFT:
            allow_buy = False
            allow_sell = True
        elif self.inventory <= -self.INVENTORY_SOFT:
            allow_buy = True
            allow_sell = False

        self._quote(Side.BUY, buy_price if allow_buy else None, now)
        self._quote(Side.SELL, sell_price if allow_sell else None, now)

    def on_private_order_update(self, event: PrivateOrderEvent) -> None:
        side = None
        quote = None
        for candidate, active in self._quotes.items():
            if active.order_id == event.order_id:
                side = candidate
                quote = active
                break
        if quote is None or side is None:
            return
        if event.status in (OrderStatus.ACCEPTED, OrderStatus.MODIFIED,
                            OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            quote.remaining = event.remaining_quantity
        if event.status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            signed = event.filled_quantity if side == Side.BUY else -event.filled_quantity
            self.inventory += signed
            if event.fill_price is not None:
                self.cash -= signed * event.fill_price
        if event.status in (OrderStatus.FILLED, OrderStatus.CANCELED):
            del self._quotes[side]
        elif event.status == OrderStatus.REJECTED:
            if event.message and event.message.startswith('cancel rejected:'):
                quote.cancel_pending = False
            else:
                del self._quotes[side]
