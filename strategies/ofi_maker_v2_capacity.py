
"""OFI v2 with full safe reversal sizing; signal and cancellation rules unchanged."""

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


class OFIMakerV2CapacityStrategy(BaseStrategy):
    def __init__(
        self,
        window_ms: int = 500,
        signal_threshold: float = 0.6,
        quote_quantity: int = 100,
        exposure_limit: int = 100,
        quote_when_neutral: bool = True,
    ) -> None:
        super().__init__()

        if (
            window_ms <= 0
            or signal_threshold < 0
            or quote_quantity <= 0
            or exposure_limit <= 0
        ):
            raise ValueError("Invalid OFI maker parameters")

        self._window_us = window_ms * 1000
        self._threshold = signal_threshold
        self._quantity = quote_quantity
        self._exposure_limit = exposure_limit
        self._quote_when_neutral = quote_when_neutral

        self._changes: deque[tuple[int, float]] = deque()
        self._ofi_sum = 0.0
        self._previous: tuple[int, int, int, int] | None = None
        self._start_us: int | None = None

        self._inventory = 0
        self._resting_id: str | None = None
        self._resting_side: Side | None = None
        self._resting_price: int | None = None
        self._remaining = 0
        self._cancel_pending = False

    @staticmethod
    def _market_touch(orders) -> tuple[int, int] | None:
        """Aggregate market-owned quantity at the best price."""
        best_price = None
        total_quantity = 0

        for order in orders:
            if order.owner != "market":
                continue

            if best_price is None:
                best_price = order.price
            elif order.price != best_price:
                break

            total_quantity += order.quantity

        if best_price is None:
            return None

        return best_price, total_quantity

    @staticmethod
    def _ofi_change(
        previous: tuple[int, int, int, int],
        current: tuple[int, int, int, int],
    ) -> float:
        """Standard level-1 OFI increment."""
        old_bid, old_bq, old_ask, old_aq = previous
        bid, bq, ask, aq = current

        bid_flow = (
            (bq if bid >= old_bid else 0)
            - (old_bq if bid <= old_bid else 0)
        )

        ask_flow = (
            -(aq if ask <= old_ask else 0)
            + (old_aq if ask >= old_ask else 0)
        )

        return float(bid_flow + ask_flow)

    def _update_ofi(
        self,
        timestamp_us: int,
        current: tuple[int, int, int, int],
    ) -> float:
        if self._start_us is None:
            self._start_us = timestamp_us

        if self._previous is not None:
            change = self._ofi_change(self._previous, current)

            if change:
                self._changes.append((timestamp_us, change))
                self._ofi_sum += change

        self._previous = current

        cutoff = timestamp_us - self._window_us

        while self._changes and self._changes[0][0] < cutoff:
            _, change = self._changes.popleft()
            self._ofi_sum -= change

        _, bid_qty, _, ask_qty = current
        avg_depth = max(1.0, (bid_qty + ask_qty) / 2.0)

        return self._ofi_sum / avg_depth

    def _cancel_current(self) -> None:
        if self._resting_id is not None and not self._cancel_pending:
            self.cancel_order(self._resting_id)
            self._cancel_pending = True

    def _clear_current(self) -> None:
        self._resting_id = None
        self._resting_side = None
        self._resting_price = None
        self._remaining = 0
        self._cancel_pending = False

    def on_order_book_change(
        self,
        snapshot: OrderBookSnapshot,
        trades: list[Trade],
    ) -> None:
        bid = self._market_touch(snapshot.bids)
        ask = self._market_touch(snapshot.asks)

        if bid is None or ask is None or bid[0] >= ask[0]:
            self._previous = None
            self._cancel_current()
            return

        timestamp_us = snapshot.timestamp_us
        current = (bid[0], bid[1], ask[0], ask[1])

        signal = self._update_ofi(timestamp_us, current)

        if timestamp_us - self._start_us < self._window_us:
            return

        # OFI direction replaces the rolling-mean signal.
        if signal > self._threshold:
            side: Side | None = Side.BUY
        elif signal < -self._threshold:
            side = Side.SELL
        elif self._quote_when_neutral:
            side = Side.BUY if self._inventory <= 0 else Side.SELL
        else:
            side = None

        if side is None:
            self._cancel_current()
            return

        # Respect the penalty-free inventory region.
        signed = self._quantity if side == Side.BUY else -self._quantity

        if abs(self._inventory + signed) > self._exposure_limit:
            # The existing remainder is not a new full-sized order. Keep its
            # queue position if its worst-case fill is still within the limit.
            if self._resting_id is not None:
                remaining_signed = (
                    self._remaining if self._resting_side == Side.BUY else -self._remaining
                )
                if abs(self._inventory + remaining_signed) > self._exposure_limit:
                    self._cancel_current()
            return

        touch = bid[0] if side == Side.BUY else ask[0]

        if self._resting_id is not None:
            if self._cancel_pending:
                return

            if self._resting_side == side:
                old_price = self._resting_price

                if old_price == touch:
                    return

                improved_past = (
                    (side == Side.BUY and touch > old_price)
                    or (side == Side.SELL and touch < old_price)
                )

                if not improved_past:
                    return

            self._cancel_current()
            return

        # No other order is live or in flight here: its ID holds the slot
        # until a terminal update, including while cancellation is pending.
        sign = 1 if side == Side.BUY else -1
        quantity = self._exposure_limit - sign * self._inventory

        order_id = self.send_order(
            OrderRequest(
                side=side,
                price=touch,
                quantity=quantity,
                order_type=OrderType.LIMIT,
            )
        )

        self._resting_id = order_id
        self._resting_side = side
        self._resting_price = touch
        self._remaining = quantity

    def on_private_order_update(
        self,
        event: PrivateOrderEvent,
    ) -> None:
        if event.order_id != self._resting_id:
            return

        if event.status in (
            OrderStatus.ACCEPTED,
            OrderStatus.MODIFIED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
        ):
            self._remaining = event.remaining_quantity

        if event.status in (
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
        ):
            delta = event.filled_quantity

            if self._resting_side == Side.BUY:
                self._inventory += delta
            else:
                self._inventory -= delta

        if event.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
        ):
            self._clear_current()

        elif event.status == OrderStatus.REJECTED:
            if (
                event.message
                and event.message.startswith("cancel rejected:")
            ):
                self._cancel_pending = False
            else:
                self._clear_current()
