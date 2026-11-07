"""Inventory cycling maker: always quote the flat-reducing side, double size to cycle through +/-100."""

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

QUOTE_QUANTITY = 100  # lots added beyond flat per cycle (a fill lands |inventory| at exactly this)
EXPOSURE_LIMIT = 100  # arena rule: |inventory| > 100 accrues penalty, so |I + s*q| stays <= this
FLOW_HALF_LIFE = 20  # events; EWMA half-life of the signed taker volume
FLOW_BAND = None  # signed lots of flow against our side beyond which we quote deeper (None disables; measured harmful)
FLOW_OFFSET = 1  # ticks beyond the touch while the flow runs against our side


class InventoryCycleStrategy(BaseStrategy):
    """Aggressive inventory cycling: buy at the bid when not long, sell at the ask when long.

    The side is purely the flat-reducing side (BUY when inventory <= 0, SELL
    when long) and the size is QUOTE_QUANTITY plus whatever inventory the
    order would unwind, so a full fill always lands |inventory| at exactly
    QUOTE_QUANTITY on the opposite side - e.g. long 100 offers 200, and its
    fill leaves short 100. Round trips harvest the spread twice per cycle
    at the maximum safe amplitude, with no price prediction at all.

    A resting order is replaced only when the desired side changes or the
    touch improves past its price, so queue priority is kept otherwise.
    """

    def __init__(
        self,
        quote_quantity: int = QUOTE_QUANTITY,
        exposure_limit: int = EXPOSURE_LIMIT,
        flow_half_life: int = FLOW_HALF_LIFE,
        flow_band: float | None = FLOW_BAND,
    ) -> None:
        super().__init__()
        self._quantity: int = quote_quantity
        self._exposure_limit: int = exposure_limit
        self._gamma: float = 1 - 0.5 ** (1 / flow_half_life)
        self._band: float | None = flow_band
        self._flow: float = 0.0
        self._inventory: int = 0
        self._order_sides: dict[str, Side] = {}
        self._resting_id: str | None = None
        self._resting_side: Side | None = None
        self._resting_price: int | None = None
        self._resting_gated = False

    def on_order_book_change(self, snapshot: OrderBookSnapshot, trades: list[Trade]) -> None:
        """Keep one order at the touch on the flat-reducing side."""
        if not snapshot.bids or not snapshot.asks:
            return

        signed_volume = 0.0
        for trade in trades:
            signed_volume += trade.quantity if trade.book_side == 'ask' else -trade.quantity
        self._flow += self._gamma * (signed_volume - self._flow)

        side: Side = Side.BUY if self._inventory <= 0 else Side.SELL
        # Flow gate: the side the taker flow is running over fills adversely
        # (measured continuation +0.14 ticks/100 events), so while it does,
        # rest that side a tick deeper instead of joining the touch.
        gated = self._band is not None and (
            (side == Side.BUY and self._flow < -self._band) or (side == Side.SELL and self._flow > self._band)
        )
        touch = snapshot.bids[0].price if side == Side.BUY else snapshot.asks[0].price
        target = touch - FLOW_OFFSET if gated and side == Side.BUY else touch + FLOW_OFFSET if gated else touch
        quantity = self._quantity + (abs(self._inventory) if (
            (side == Side.BUY and self._inventory < 0) or (side == Side.SELL and self._inventory > 0)
        ) else 0)
        if self._resting_id is not None:
            if self._resting_side == side and self._resting_gated == gated:
                if self._resting_price == target:
                    return  # already quoted at the target
                improved_past = (side == Side.BUY and target > self._resting_price) or (
                    side == Side.SELL and target < self._resting_price
                )
                if not improved_past:
                    return  # still at the touch, keep queue priority
            self.cancel_order(self._resting_id)
            return  # wait for the CANCELED event, then re-quote

        order_id = self.send_order(
            OrderRequest(
                side=side,
                price=target,
                quantity=quantity,
                order_type=OrderType.LIMIT,
            )
        )
        self._order_sides[order_id] = side
        self._resting_id, self._resting_side, self._resting_price = order_id, side, target
        self._resting_gated = gated

    def on_private_order_update(self, event: PrivateOrderEvent) -> None:
        """Accumulate inventory on fills; free the slot once the order is terminal."""
        if event.status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            side = self._order_sides.get(event.order_id)
            if side is not None:
                self._inventory += event.filled_quantity if side == Side.BUY else -event.filled_quantity

        if event.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED):
            self._order_sides.pop(event.order_id, None)
            if self._resting_id == event.order_id:
                self._resting_id, self._resting_side, self._resting_price = None, None, None
