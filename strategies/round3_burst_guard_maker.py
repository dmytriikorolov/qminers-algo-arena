"""Round 3 burst-guard market maker.

Independent hypothesis: 500 ms bursts of executed market-taker orders predict
short-lived price continuation. Protect only the inventory-*growing* quote on
its toxic side, while keeping a flattening order at the touch.

No lookahead, tape-only data or external packages. At most one outstanding
LIMIT order per side; no replacement until the cancel/fill is confirmed.
"""

from __future__ import annotations

from collections import deque

from simulator.models import (
    OrderBookSnapshot, OrderRequest, OrderStatus, OrderType,
    PrivateOrderEvent, Side, Trade,
)
from simulator.strategy import BaseStrategy


class Round3BurstGuardMaker(BaseStrategy):
    WINDOW_US = 500_000
    WARMUP_US = 500_000
    TRIGGER_COUNT = 3
    BURST_HOLD_US = 200_000
    MAX_SPREAD = 8
    LIMIT = 100
    QUOTE_LOT = 100
    FLIP_ALLOWANCE = 20
    SAFE_GROW_QTY = 30
    REQUOTE_AGE_US = 500_000
    REQUOTE_LAG_TICKS = 2
    MIN_ORDER_INTERVAL_US = 40_000

    def __init__(self):
        super().__init__()
        self.inventory = 0
        self.cash = 0
        # Each trade batch contains total market taker signed count for a time.
        self._flow = deque()
        self._flow_sum = 0
        self._first_us = None
        self._danger_until = {Side.BUY: 0, Side.SELL: 0}
        # side -> mutable [id, price, remaining, submitted_us, cancel_pending]
        self._orders = {}
        self._last_send = {Side.BUY: -10**15, Side.SELL: -10**15}

    @staticmethod
    def _touch(orders):
        """Return best price and available market volume; ignore our own quotes."""
        price = None
        quantity = 0
        for o in orders:
            if o.owner != 'market':
                continue
            if price is None:
                price = o.price
            elif o.price != price:
                break
            quantity += o.quantity
        if price is None:
            return None
        return price, quantity

    def _update_flow(self, now, trades):
        # All matches for one aggressive market order count as one observation.
        # Grouping by taker id avoids heavily sweeping orders being overcounted.
        count = 0
        seen = set()
        for t in trades:
            if t.taker_owner != 'market' or t.taker_order_id in seen:
                continue
            seen.add(t.taker_order_id)
            count += 1 if t.book_side == 'ask' else -1
        if count:
            self._flow.append((now, count))
            self._flow_sum += count
        cutoff = now - self.WINDOW_US
        while self._flow and self._flow[0][0] < cutoff:
            _, expired = self._flow.popleft()
            self._flow_sum -= expired
        # Side.BUY is toxic when aggressive sells dominate; Side.SELL when
        # aggressive buys dominate. Hold the gate briefly to prevent flicker.
        if self._flow_sum >= self.TRIGGER_COUNT:
            self._danger_until[Side.SELL] = max(
                self._danger_until[Side.SELL], now + self.BURST_HOLD_US
            )
        elif self._flow_sum <= -self.TRIGGER_COUNT:
            self._danger_until[Side.BUY] = max(
                self._danger_until[Side.BUY], now + self.BURST_HOLD_US
            )

    def _cancel(self, side):
        current = self._orders.get(side)
        if current is not None and not current[4]:
            self.cancel_order(current[0])
            current[4] = True

    def _desired(self, side, market_price, now):
        sign = 1 if side == Side.BUY else -1
        reducing = sign * self.inventory < 0
        danger = now < self._danger_until[side]
        if danger and not reducing:
            return None
        capacity = max(0, self.LIMIT - sign * self.inventory)
        quantity = min(self.QUOTE_LOT, capacity)
        if reducing:
            # Flattening may proceed at the touch even in toxic flow.
            # Only permit a small flip into fresh opposing inventory.
            quantity = min(quantity, abs(self.inventory) + self.FLIP_ALLOWANCE)
        elif now < self._danger_until[side.opposite]:
            # Following a burst, the non-toxic quote may still fill on reversal.
            # Reduce its size to avoid using the whole inventory budget.
            quantity = min(quantity, self.SAFE_GROW_QTY)
        if quantity <= 0:
            return None
        return market_price, quantity

    def _reconcile(self, side, desired, now):
        current = self._orders.get(side)
        if desired is None:
            self._cancel(side)
            return
        price, quantity = desired
        if current is not None:
            if current[4]:
                return
            old_price = current[1]
            # A resting quote that moved *inside* the current market touch is
            # dangerously exposed: cancel immediately. Otherwise retain queue
            # priority until it is stale by >=2 ticks and >=500ms.
            unsafe = (old_price > price if side == Side.BUY else old_price < price)
            stale = (now - current[3] >= self.REQUOTE_AGE_US
                     and abs(old_price - price) >= self.REQUOTE_LAG_TICKS)
            sign = 1 if side == Side.BUY else -1
            hard_room = max(0, self.LIMIT - sign * self.inventory)
            # Do not sacrifice an already-established queue position merely
            # to shrink the *safe* side of a fresh flow burst. Shrink only
            # when hard inventory room or flip protection requires it.
            unsafe_quantity = current[2] > hard_room or (
                sign * self.inventory < 0 and current[2] > quantity
            )
            if unsafe or stale or unsafe_quantity:
                self._cancel(side)
            return
        if now - self._last_send[side] < self.MIN_ORDER_INTERVAL_US:
            return
        # Existing same-side order is always terminal here. Waiting for
        # private confirmation avoids racing old and new quantities over +100.
        order_id = self.send_order(OrderRequest(
            side=side, price=price, quantity=quantity, order_type=OrderType.LIMIT
        ))
        self._orders[side] = [order_id, price, quantity, now, False]
        self._last_send[side] = now

    def on_order_book_change(self, snapshot: OrderBookSnapshot,
                             trades: list[Trade]) -> None:
        now = snapshot.timestamp_us
        if self._first_us is None:
            self._first_us = now
        self._update_flow(now, trades)
        bid = self._touch(snapshot.bids)
        ask = self._touch(snapshot.asks)
        if bid is None or ask is None or bid[0] >= ask[0]:
            self._cancel(Side.BUY)
            self._cancel(Side.SELL)
            return
        if now - self._first_us < self.WARMUP_US or ask[0] - bid[0] > self.MAX_SPREAD:
            self._cancel(Side.BUY)
            self._cancel(Side.SELL)
            return
        self._reconcile(Side.BUY, self._desired(Side.BUY, bid[0], now), now)
        self._reconcile(Side.SELL, self._desired(Side.SELL, ask[0], now), now)

    def on_private_order_update(self, event: PrivateOrderEvent) -> None:
        for side, order in self._orders.items():
            if order[0] != event.order_id:
                continue
            status = event.status
            if status in (OrderStatus.ACCEPTED, OrderStatus.MODIFIED,
                          OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
                order[2] = event.remaining_quantity
            if status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
                signed = event.filled_quantity if side == Side.BUY else -event.filled_quantity
                self.inventory += signed
                if event.fill_price is not None:
                    self.cash -= signed * event.fill_price
            if status in (OrderStatus.FILLED, OrderStatus.CANCELED):
                del self._orders[side]
            elif status == OrderStatus.REJECTED:
                if event.message and event.message.startswith('cancel rejected:'):
                    order[4] = False
                else:
                    del self._orders[side]
            break
