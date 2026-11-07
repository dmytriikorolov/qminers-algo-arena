"""Two-sided passive maker: rests a bid and an ask at the touch, sides gated by the mean-reversion signal."""

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
DEVIATION_DEADBAND = 1  # t in ticks: |mid - mean| beyond this only the reversion side quotes
SIDE_QUANTITY = 100  # lots per resting order, per side (two rest at once, so a single fill moves |I| by this)
EXPOSURE_LIMIT = 100  # arena rule: |inventory| > 100 accrues penalty, so |I + s*q| stays <= this
SKEW_BAND = 0  # within the deadband, a side growing |inventory| quotes only while |I| stays under this band

_EMPTY = 0  # no order on the side
_PLACING = 1  # order sent, waiting out the accept delay
_RESTING = 2  # live in the book (possibly partially filled)
_CANCELLING = 3  # cancel sent, waiting for its confirmation (a fill can still win the race)


class TwoSidedMakerStrategy(BaseStrategy):
    """Market maker quoting both sides of the book at once.

    Two independent quote slots, one per side, each with its own order
    lifecycle; the mean-reversion signal decides which sides are wanted:

    - when |mid - mean| exceeds the deadband, only the reversion side quotes
      (mid rich: ask only; mid cheap: bid only) - the same fade as the
      one-sided `mean_maker`, which beyond the deadband is also single-sided;
    - within the deadband both sides quote, but a side that would grow
      |inventory| may rest only while |inventory| stays inside the skew band
      (SKEW_BAND); once it is left, only the inventory-reducing side keeps
      quoting - the two-sided form of mean_maker's flat-reduction side
      choice, with the band choosing how far from flat both sides may rest.

    Each side keeps its queue priority: a resting order is replaced only when
    its side is no longer wanted or the touch improves past its price. The
    sides never wait on each other, so a fill on one side leaves the other
    resting, and the per-side exposure gate (checked against the inventory at
    placement time, with one order per side) guarantees no single fill can
    push |inventory| into the penalty zone.
    """

    def __init__(
        self,
        window_size: int = WINDOW_SIZE,
        deviation_deadband: int = DEVIATION_DEADBAND,
        side_quantity: int = SIDE_QUANTITY,
        exposure_limit: int = EXPOSURE_LIMIT,
        skew_band: int = SKEW_BAND,
    ) -> None:
        super().__init__()
        self._window: deque[float] = deque(maxlen=window_size)
        self._deadband: int = deviation_deadband
        self._quantity: int = side_quantity
        self._exposure_limit: int = exposure_limit
        self._skew_band: int = skew_band
        self._inventory: int = 0
        self._order_sides: dict[str, Side] = {}
        sides = (Side.BUY, Side.SELL)
        self._order: dict[Side, str | None] = dict.fromkeys(sides)
        self._price: dict[Side, int | None] = dict.fromkeys(sides)
        self._phase: dict[Side, int] = dict.fromkeys(sides, _EMPTY)

    def on_order_book_change(self, snapshot: OrderBookSnapshot, trades: list[Trade]) -> None:
        """Update the mid-price window and keep both sides quoting at the touch."""
        if not snapshot.bids or not snapshot.asks:
            return

        mid = (snapshot.bids[0].price + snapshot.asks[0].price) / 2
        self._window.append(mid)
        if len(self._window) < self._window.maxlen:
            return

        mean = sum(self._window) / len(self._window)
        deviation = mid - mean
        if deviation > self._deadband:
            want: dict[Side, bool] = {Side.BUY: False, Side.SELL: True}  # mid rich: fade up
        elif deviation < -self._deadband:
            want = {Side.BUY: True, Side.SELL: False}  # mid cheap: fade down
        else:
            want = {Side.BUY: True, Side.SELL: True}

        # A single fill must never push |inventory| into the penalty zone
        # (the hard bound, applied to every quote); within the deadband the
        # skew band tightens it for the side that would grow |inventory|, so
        # only the reducing side quotes once the band is left - keeping the
        # position small through the noise instead of feeding momentum.
        bid_cap = min(self._exposure_limit - self._quantity, self._skew_band)
        ask_floor = max(self._quantity - self._exposure_limit, -self._skew_band)
        if deviation > self._deadband or deviation < -self._deadband:
            if self._inventory + self._quantity > self._exposure_limit:
                want[Side.BUY] = False
            if self._inventory - self._quantity < -self._exposure_limit:
                want[Side.SELL] = False
        else:
            if self._inventory > bid_cap:
                want[Side.BUY] = False
            if self._inventory < ask_floor:
                want[Side.SELL] = False

        touches = {Side.BUY: snapshot.bids[0].price, Side.SELL: snapshot.asks[0].price}
        for side in (Side.BUY, Side.SELL):
            self._manage(side, want[side], touches[side])

    def _manage(self, side: Side, wanted: bool, touch: int) -> None:
        """Reconcile one side's resting order with whether the side is wanted at `touch`."""
        phase = self._phase[side]
        if phase in (_PLACING, _CANCELLING):
            return  # an action is in flight; the terminal event frees the slot

        if not wanted:
            if phase == _RESTING:
                self.cancel_order(self._order[side])
                self._phase[side] = _CANCELLING
            return

        if phase == _RESTING:
            resting_price = self._price[side]
            if resting_price == touch:
                return  # already quoted at the touch
            improved_past = (side == Side.BUY and touch > resting_price) or (
                side == Side.SELL and touch < resting_price
            )
            if not improved_past:
                return  # still at the touch, keep queue priority
            self.cancel_order(self._order[side])
            self._phase[side] = _CANCELLING
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
        self._order[side] = order_id
        self._price[side] = touch
        self._phase[side] = _PLACING

    def on_private_order_update(self, event: PrivateOrderEvent) -> None:
        """Accumulate inventory on fills; free the side's slot once its order is terminal."""
        side = self._order_sides.get(event.order_id)
        if side is None:
            return  # unknown id, e.g. a cancel that lost the race against a fill

        if event.status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            self._inventory += event.filled_quantity if side == Side.BUY else -event.filled_quantity

        if event.status is OrderStatus.ACCEPTED:
            if self._phase[side] == _PLACING and self._order[side] == event.order_id:
                self._phase[side] = _RESTING
            return

        if event.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED):
            self._order_sides.pop(event.order_id, None)
            if self._order[side] == event.order_id:
                self._order[side] = None
                self._price[side] = None
                self._phase[side] = _EMPTY
