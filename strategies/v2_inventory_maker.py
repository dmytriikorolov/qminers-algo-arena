"""Small inventory maker with pending exposure reservations and liquidation halt."""

from math import ceil, exp, floor, sqrt

from simulator.models import OrderBookSnapshot, OrderRequest, OrderStatus, OrderType, PrivateOrderEvent, Side, Trade
from simulator.strategy import BaseStrategy


class InventoryMakerStrategy(BaseStrategy):
    LOT = 1
    LIMIT = 2
    SIGNAL_WEIGHT = 0.0
    SKEW = 0.5
    VOL_WEIGHT = 1.0
    VOL_TAU_US = 1_000_000
    MAX_SPREAD = 6
    MAX_AGE_US = 1_000_000
    MAX_DRAWDOWN = 20
    EXIT_RETRY_US = 100_000

    def __init__(self) -> None:
        super().__init__()
        self.inventory = 0
        self.cash = 0
        self.peak_equity = 0
        self.halted = False
        self.retry_at = 0
        self.orders = {}
        self.last_mid = None
        self.last_time = None
        self.variance = 0.0

    def on_order_book_change(self, snapshot: OrderBookSnapshot, trades: list[Trade]) -> None:
        now = snapshot.timestamp_us
        bids = [o for o in snapshot.bids if o.owner == 'market']
        asks = [o for o in snapshot.asks if o.owner == 'market']
        targets = {}
        exit_book = bids if self.inventory > 0 else asks
        remaining = abs(self.inventory)
        value = 0
        exit_price = None
        for order in exit_book:
            if remaining == 0:
                break
            amount = min(remaining, order.quantity)
            remaining -= amount
            value += amount * order.price
            exit_price = order.price
        if remaining == 0:
            equity = self.cash + (value if self.inventory > 0 else -value)
            self.peak_equity = max(self.peak_equity, equity)
            if self.peak_equity - equity >= self.MAX_DRAWDOWN:
                self.halted = True
        if self.halted:
            for order_id, state in list(self.orders.items()):
                if state[4] and not state[5]:
                    state[5] = True
                    self.cancel_order(order_id)
            # Wait for every live/pending quote to terminate before liquidating.
            if not self.orders and self.inventory and exit_price is not None and now >= self.retry_at:
                side = Side.SELL if self.inventory > 0 else Side.BUY
                order_id = self.send_order(OrderRequest(
                    side=side, price=exit_price, quantity=abs(self.inventory), order_type=OrderType.IOC))
                self.orders[order_id] = [side, exit_price, abs(self.inventory), now, False, False]
                self.retry_at = now + self.EXIT_RETRY_US
            return
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
            sign = 1 if state[0] == Side.BUY else -1
            self.inventory += event.filled_quantity * sign
            self.cash -= event.filled_quantity * sign * event.fill_price
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
