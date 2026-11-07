"""Flow-following maker: rests the side opposite the taker flow, catching counter-flow dips.

Signal: an EWMA of signed taker volume (buy-taker flow positive). Measured on
round1 (/tmp/opencode/signal_research.py): after the flow EWMA leaves its band
the mid continues ~0.14 ticks over the next 100 events in the flow direction
(t ~= 46 across burst regimes) - momentum continuation, an order of magnitude
stronger than every other signal tested, while the deviation-from-window-mean
signal measured ~zero.

A maker cannot choose which side fills, the flow does: during buy-flow the
ask fills readily but adversely (the drift continues up), while the bid fills
only on counter-flow dips that revert with the regime. So the strategy quotes
the cold side, opposite the flow:

- flow > +FLOW_BAND: buy regime -> rest the BID, dip fills go long before the drift;
- flow < -FLOW_BAND: sell regime -> rest the ASK, bounce fills go short before the drift;
- inside the band: the flat-reducing side, as in `mean_maker`;
- a flow flip is the leg's peak/bottom ("second direction change"): the quoted
  side swaps, unwinding the position into the new leg.

Guardrails are mean_maker's: touch-joined passive quotes, requote only when
the side changes or the touch improves past the resting price, and the hard
exposure bound so no single fill can push |inventory| into the penalty zone.
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

FLOW_HALF_LIFE = 20  # events; EWMA half-life of the signed taker volume
FLOW_BAND = 1.3  # signed lots the flow must reach to set a regime (round1 |flow| q60 ~= 1.28)
QUOTE_QUANTITY = 100  # lots per resting order (a single fill must not breach the penalty zone)
EXPOSURE_LIMIT = 100  # arena rule: |inventory| > 100 accrues penalty, so |I + s*q| stays <= this


class FlowMakerStrategy(BaseStrategy):
    """Market maker whose quoted side is set by taker-flow momentum.

    One limit order at a time, joined to the touch (the `mean_maker` skeleton
    with the signal swapped): the side is the flow-opposite side beyond the
    band, else the flat-reducing side. A resting order is replaced only when
    the desired side changes or the touch improves past its price, so queue
    priority is kept otherwise. Fills earn the spread on counter-flow dips
    instead of paying it, and inventory rides the leg until the flow flips.
    """

    def __init__(
        self,
        flow_half_life: int = FLOW_HALF_LIFE,
        flow_band: float = FLOW_BAND,
        quote_quantity: int = QUOTE_QUANTITY,
        exposure_limit: int = EXPOSURE_LIMIT,
    ) -> None:
        super().__init__()
        self._gamma: float = 1 - 0.5 ** (1 / flow_half_life)
        self._band: float = flow_band
        self._quantity: int = quote_quantity
        self._exposure_limit: int = exposure_limit
        self._flow: float = 0.0
        self._inventory: int = 0
        self._outstanding: int = 0  # orders sent but not yet terminal
        self._order_sides: dict[str, Side] = {}
        self._resting_id: str | None = None
        self._resting_side: Side | None = None
        self._resting_price: int | None = None

    def on_order_book_change(self, snapshot: OrderBookSnapshot, trades: list[Trade]) -> None:
        """Update the flow estimate and keep one passive quote at the touch."""
        if not snapshot.bids or not snapshot.asks:
            return

        signed_volume = 0.0
        for trade in trades:
            signed_volume += trade.quantity if trade.book_side == 'ask' else -trade.quantity
        self._flow += self._gamma * (signed_volume - self._flow)

        if self._outstanding > 0:
            return

        if self._flow > self._band:
            side: Side = Side.BUY  # buy regime: rest the bid, catch the dips
        elif self._flow < -self._band:
            side = Side.SELL  # sell regime: rest the ask, catch the bounces
        else:
            side = Side.BUY if self._inventory <= 0 else Side.SELL

        # A single fill must never push |inventory| into the penalty zone;
        # stand down (keeping any existing resting order) if it could.
        signed = self._quantity if side == Side.BUY else -self._quantity
        if abs(self._inventory + signed) > self._exposure_limit:
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
                    return  # still at the touch, keep queue priority
            self.cancel_order(self._resting_id)
            return  # wait for the CANCELED event, then re-quote

        order_id = self.send_order(
            OrderRequest(
                side=side,
                price=touch,
                quantity=self._quantity,
                order_type=OrderType.LIMIT,
            )
        )
        self._order_sides[order_id] = side
        self._resting_id, self._resting_side, self._resting_price = order_id, side, touch

    def on_private_order_update(self, event: PrivateOrderEvent) -> None:
        """Accumulate inventory on fills; free the slot once the order is terminal."""
        if event.status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            side = self._order_sides.get(event.order_id)
            if side is not None:
                self._inventory += event.filled_quantity if side == Side.BUY else -event.filled_quantity

        if event.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED):
            self._order_sides.pop(event.order_id, None)
            self._outstanding = max(0, self._outstanding - 1)
            if self._resting_id == event.order_id:
                self._resting_id, self._resting_side, self._resting_price = None, None, None
