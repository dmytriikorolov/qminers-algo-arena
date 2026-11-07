"""Small market quotes with causal microprice, volatility and reserved exposure."""

from math import ceil, exp, floor, sqrt

from simulator.models import OrderBookSnapshot, OrderRequest, OrderStatus, OrderType, PrivateOrderEvent, Side, Trade
from simulator.strategy import BaseStrategy


class PlaygroundQuotesStrategy(BaseStrategy):
    LOT = 2
    LIMIT = 10
    SIGNAL_WEIGHT = 0.5
    SKEW = 0.15
    VOL_WEIGHT = 1.0
    VOL_TAU_US = 1_000_000
    MAX_SPREAD = 6
    MAX_AGE_US = 1_000_000

    def __init__(self) -> None:
        super().__init__()
        self.inventory = 0
        self.orders = {}
        self.last_mid = None
        self.last_time = None
        self.variance = 0.0

    def on_order_book_change(self, snapshot: OrderBookSnapshot, trades: list[Trade]) -> None:
        now = snapshot.timestamp_us
        bids = [o for o in snapshot.bids if o.owner == 'market']
        asks = [o for o in snapshot.asks if o.owner == 'market']
        targets = {}
        if bids and asks:
            bid, ask = bids[0].price, asks[0].price
            spread = ask - bid
            mid = (bid + ask) / 2
            if self.last_time is not None and now > self.last_time:
                elapsed = now - self.last_time
                decay = exp(-elapsed / self.VOL_TAU_US)
                rate = (mid - self.last_mid) ** 2 * 1_000_000 / elapsed
                self.variance = decay * self.variance + (1 - decay) * rate
            self.last_mid, self.last_time = mid, now
            if 0 < spread <= self.MAX_SPREAD:
                bid_size = sum(o.quantity for o in bids if o.price == bid)
                ask_size = sum(o.quantity for o in asks if o.price == ask)
                imbalance = (bid_size - ask_size) / (bid_size + ask_size)
                microprice = mid + spread * imbalance / 2
                center = mid + self.SIGNAL_WEIGHT * (microprice - mid) - self.SKEW * self.inventory
                width = max(spread / 2, 0.5 + self.VOL_WEIGHT * sqrt(self.variance * 0.005))
                targets[Side.BUY] = max(1, min(bid, floor(center - width)))
                targets[Side.SELL] = max(ask, ceil(center + width))

        # A cancel reserves its remaining quantity until the terminal callback.
        for order_id, state in list(self.orders.items()):
            side, price, remaining, sent_at, accepted, canceling = state
            target = targets.get(side)
            room = self.LIMIT - self.inventory if side == Side.BUY else self.LIMIT + self.inventory
            if accepted and not canceling and (target != price or room < remaining or now - sent_at >= self.MAX_AGE_US):
                state[5] = True
                self.cancel_order(order_id)

        for side, price in targets.items():
            if any(state[0] == side for state in self.orders.values()):
                continue
            room = self.LIMIT - self.inventory if side == Side.BUY else self.LIMIT + self.inventory
            quantity = min(self.LOT, room)
            if quantity <= 0:
                continue
            order_id = self.send_order(OrderRequest(
                side=side, price=price, quantity=quantity, order_type=OrderType.LIMIT))
            self.orders[order_id] = [side, price, quantity, now, False, False]

    def on_private_order_update(self, event: PrivateOrderEvent) -> None:
        state = self.orders.get(event.order_id)
        if state is None:
            return
        if event.status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            self.inventory += event.filled_quantity * (1 if state[0] == Side.BUY else -1)
            state[2] = event.remaining_quantity
        elif event.status == OrderStatus.ACCEPTED:
            state[4] = True
        elif event.status == OrderStatus.MODIFIED:
            state[2] = event.remaining_quantity
        if event.status in (OrderStatus.FILLED, OrderStatus.CANCELED):
            del self.orders[event.order_id]
        elif event.status == OrderStatus.REJECTED:
            if not state[4]:
                del self.orders[event.order_id]
            else:
                state[5] = False
