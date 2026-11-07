"""Adaptive full two-sided maker: full_two_sided + flip split + fast requote + volatility-scaled limit.

Measured 2026-11-07 (round1 / round2_public):
    full_two_sided              458,421 / -200,244
    adaptive_maker (this file)  506,735 / +110,448

Layers on top of `full_two_sided` (bid LIMIT-I and ask LIMIT+I at the best
*market* price, the |I|-growing side one tick deeper when the top-of-book
imbalance is against it):

1. Flip split. At +100 the ask is 200 lots: 100 flatten, 100 flip to -100.
   The flip part fills only when a large taker clears the level - the worst
   fills. When the own-side imbalance is below FLIP_GATE, the touch order is
   SHRUNK with modify_order (keeps queue priority) to flat + FLIP_KEEP and
   the rest rests one tick deeper.
2. Fast requote. Orders that the touch has moved past are cancelled and the
   replacement is sent in the same callback instead of after the cancel
   confirms (5 ms instead of 10 ms to the new level). If the race still lets
   both fill and |I| passes LIMIT, an IOC immediately trades the excess away
   (cost on round1: 50 in penalty over 200 minutes).
3. Volatility switch. EWMA (VOL_HALF_LIFE s) of squared 1-second mid
   returns; the inventory limit scales linearly from LIMIT at VOL_LO to 0 at
   VOL_HI, so in a crash the strategy only unwinds and stops adding. round1
   (1 s vol ~0.9) never triggers it; round2 (crashes at 4-8 ticks/s) is
   where all the losses came from.
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
IMB_GATE = -0.8  # own-side imbalance below this -> the |I|-growing side rests one tick deeper
FLIP_GATE = -0.7  # own-side imbalance below this -> the reducing side's flip part rests one tick deeper
FLIP_KEEP = 40  # lots of the flip part kept at the touch while the flip gate is on
VOL_HALF_LIFE = 10  # seconds; EWMA half-life of squared 1 s mid returns
VOL_LO = 2.0  # ticks/s: full limit at or below this volatility
VOL_HI = 3.5  # ticks/s: zero limit (unwind only) at or above this volatility
RESCUE_SLIP = 2  # ticks through the touch for the over-limit rescue IOC

# order record fields
_SIDE, _PX, _REM, _CXL, _SEQ, _PMOD, _ACC = range(7)


class AdaptiveMakerStrategy(BaseStrategy):
    """Full-capacity two-sided maker with flip split, fast requote and a volatility switch."""

    def __init__(
        self,
        limit: int = LIMIT,
        imb_gate: float | None = IMB_GATE,
        flip_gate: float | None = FLIP_GATE,
        flip_keep: int = FLIP_KEEP,
        vol_half_life: float = VOL_HALF_LIFE,
        vol_lo: float | None = VOL_LO,
        vol_hi: float = VOL_HI,
    ) -> None:
        super().__init__()
        self._limit = limit
        self._imb_gate = imb_gate
        self._flip_gate = flip_gate
        self._flip_keep = flip_keep
        self._vol_lo = vol_lo
        self._vol_hi = vol_hi
        self._vol_gamma = 1 - 0.5 ** (1 / vol_half_life)
        self._var = 0.0
        self._sec: int | None = None
        self._last_mid = 0.0
        self._eff_limit = limit
        self._inventory = 0
        self._best: tuple[int, int] | None = None
        self._seq = 0
        self._orders: dict[str, list] = {}
        self._iocs: dict[str, int] = {}  # rescue IOC id -> signed remaining quantity

    # ------------------------------------------------------------------ market data

    def on_order_book_change(self, snapshot: OrderBookSnapshot, trades: list[Trade]) -> None:
        """Update volatility, then reconcile both sides against their targets."""
        best = {}
        for side, book in ((Side.BUY, snapshot.bids), (Side.SELL, snapshot.asks)):
            price = None
            quantity = 0
            for order in book:
                if order.owner != 'market':
                    continue
                if price is None:
                    price = order.price
                elif order.price != price:
                    break
                quantity += order.quantity
            if price is None:
                return
            best[side] = (price, quantity)
        (bid_px, bid_qty), (ask_px, ask_qty) = best[Side.BUY], best[Side.SELL]
        self._best = (bid_px, ask_px)
        self._update_volatility(snapshot.timestamp_us, (bid_px + ask_px) / 2)

        imbalance = (bid_qty - ask_qty) / (bid_qty + ask_qty)
        for side, own_imb in ((Side.BUY, imbalance), (Side.SELL, -imbalance)):
            step = -1 if side == Side.BUY else 1
            touch = best[side][0]
            deep = touch + step
            if side == Side.BUY:
                adding = self._inventory >= 0
                room = max(0, self._eff_limit - self._inventory, -self._inventory)
            else:
                adding = self._inventory <= 0
                room = max(0, self._eff_limit + self._inventory, self._inventory)
            if adding:
                gated = self._imb_gate is not None and own_imb < self._imb_gate
                touch_qty = 0 if gated else room
            elif self._flip_gate is not None and own_imb < self._flip_gate:
                touch_qty = min(room, abs(self._inventory) + self._flip_keep)
            else:
                touch_qty = room
            self._reconcile(side, touch, {touch: touch_qty, deep: room - touch_qty})

    def _update_volatility(self, timestamp_us: int, mid: float) -> None:
        if self._vol_lo is None:
            return
        sec = timestamp_us // 1_000_000
        if self._sec is None:
            self._sec, self._last_mid = sec, mid
            return
        if sec <= self._sec:
            return
        for _ in range(min(sec - self._sec - 1, 60)):  # quiet seconds count as zero returns
            self._var *= 1 - self._vol_gamma
        ret = mid - self._last_mid
        self._var += self._vol_gamma * (ret * ret - self._var)
        self._sec, self._last_mid = sec, mid
        vol = self._var**0.5
        if vol <= self._vol_lo:
            fraction = 1.0
        elif vol >= self._vol_hi:
            fraction = 0.0
        else:
            fraction = (self._vol_hi - vol) / (self._vol_hi - self._vol_lo)
        self._eff_limit = int(self._limit * fraction)

    # ------------------------------------------------------------------ order management

    def _reconcile(self, side: Side, touch: int, want: dict[int, int]) -> None:
        """Bring the side's resting orders to `want` {price: quantity}; oldest orders keep priority."""
        live = sorted(
            ((oid, o) for oid, o in self._orders.items() if o[_SIDE] == side and not o[_CXL]),
            key=lambda item: item[1][_SEQ],
        )
        have = dict.fromkeys(want, 0)
        for order_id, order in live:
            price = order[_PX]
            if want.get(price, 0) <= 0:
                self.cancel_order(order_id)
                order[_CXL] = True
                continue
            effective = order[_PMOD] if order[_PMOD] is not None else order[_REM]
            if have[price] + effective <= want[price]:
                have[price] += effective
            elif have[price] < want[price]:
                new_qty = want[price] - have[price]
                if new_qty < order[_REM] and order[_PMOD] != new_qty:
                    self.modify_order(order_id, new_qty)  # shrink, keeping queue priority
                    order[_PMOD] = new_qty
                have[price] = want[price]
            else:
                self.cancel_order(order_id)
                order[_CXL] = True

        # Cancels of orders the touch has moved past can only fill if the whole
        # new level is swept within the 5 ms race, so their quantity is released
        # now (fast requote); the rescue IOC covers that rare overshoot.
        step = 1 if side == Side.BUY else -1
        committed = sum(
            o[_REM]
            for o in self._orders.values()
            if o[_SIDE] == side and not (o[_CXL] and step * (touch - o[_PX]) > 0)
        )
        free = sum(want.values()) - committed
        for price in want:  # touch first, then deep
            need = min(want[price] - have[price], free)
            if need > 0:
                order_id = self.send_order(
                    OrderRequest(side=side, price=price, quantity=need, order_type=OrderType.LIMIT)
                )
                self._seq += 1
                self._orders[order_id] = [side, price, need, False, self._seq, None, False]
                free -= need

    def _rescue(self) -> None:
        """Trade any inventory beyond the hard limit away immediately with an IOC."""
        if abs(self._inventory) <= self._limit or self._best is None:
            return
        excess = abs(self._inventory) - self._limit - sum(abs(q) for q in self._iocs.values())
        if excess <= 0:
            return
        if self._inventory > 0:
            price = max(1, self._best[0] - RESCUE_SLIP)
            order_id = self.send_order(OrderRequest(side=Side.SELL, price=price, quantity=excess, order_type=OrderType.IOC))
            self._iocs[order_id] = -excess
        else:
            price = self._best[1] + RESCUE_SLIP
            order_id = self.send_order(OrderRequest(side=Side.BUY, price=price, quantity=excess, order_type=OrderType.IOC))
            self._iocs[order_id] = excess

    def on_private_order_update(self, event: PrivateOrderEvent) -> None:
        """Track inventory, remaining quantities, modifies and terminal states."""
        status = event.status
        if event.order_id in self._iocs:
            if status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
                sign = 1 if self._iocs[event.order_id] > 0 else -1
                self._inventory += sign * event.filled_quantity
                self._iocs[event.order_id] = sign * event.remaining_quantity
            if status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED):
                del self._iocs[event.order_id]
            return

        order = self._orders.get(event.order_id)
        if order is None:
            return
        if status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            self._inventory += event.filled_quantity if order[_SIDE] == Side.BUY else -event.filled_quantity
            order[_REM] = event.remaining_quantity
            self._rescue()
        elif status == OrderStatus.MODIFIED:
            order[_REM] = event.remaining_quantity
            order[_PMOD] = None
        elif status == OrderStatus.ACCEPTED:
            order[_ACC] = True
            return
        elif status == OrderStatus.REJECTED and order[_ACC]:
            order[_PMOD] = None  # a rejected modify/cancel: the order itself is still live
            return
        if status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED):
            del self._orders[event.order_id]
