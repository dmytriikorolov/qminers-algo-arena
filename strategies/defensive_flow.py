"""Small confirmed-flow entries with independent exits and a drawdown halt."""

from simulator.models import OrderBookSnapshot, OrderRequest, OrderStatus, OrderType, PrivateOrderEvent, Side, Trade
from simulator.strategy import BaseStrategy


class DefensiveFlowStrategy(BaseStrategy):
    LOT = 2
    LIMIT = 5
    MAX_SPREAD = 4
    CONFIRM_US = 100_000
    SIGNAL_TTL_US = 2_000_000
    MAX_HOLD_US = 5_000_000
    COOLDOWN_US = 1_000_000
    EXIT_RETRY_US = 100_000
    MAX_TRADE_LOSS = 12
    MAX_DRAWDOWN = 30

    def __init__(self) -> None:
        super().__init__()
        self.inventory = 0
        self.cash = 0
        self.order_id = None
        self.order_side = None
        self.holding_since = None
        self.entry_cash = 0
        self.peak_equity = 0
        self.halted = False
        self.exiting = False
        self.cooldown_until = 0
        self.retry_at = 0
        self.signal = None

    def _send(self, side, price, quantity):
        self.order_side = side
        self.order_id = self.send_order(OrderRequest(
            side=side, price=price, quantity=quantity, order_type=OrderType.IOC))

    def on_order_book_change(self, snapshot: OrderBookSnapshot, trades: list[Trade]) -> None:
        now = snapshot.timestamp_us
        bids = [o for o in snapshot.bids if o.owner == 'market']
        asks = [o for o in snapshot.asks if o.owner == 'market']

        # Mark only against executable visible market liquidity, never the mid.
        equity = self.cash if self.inventory == 0 else None
        exit_book = bids if self.inventory > 0 else asks
        remaining = abs(self.inventory)
        value = 0
        exit_price = None
        for order in exit_book:
            if remaining == 0:
                break
            amount = min(remaining, order.quantity)
            value += amount * order.price
            remaining -= amount
            exit_price = order.price
        if self.inventory and remaining == 0:
            equity = self.cash + (value if self.inventory > 0 else -value)
        if equity is not None:
            self.peak_equity = max(self.peak_equity, equity)
            if self.peak_equity - equity >= self.MAX_DRAWDOWN:
                self.halted = True
            if self.inventory and equity - self.entry_cash <= -self.MAX_TRADE_LOSS:
                self.exiting = True
        if self.inventory and (self.halted or now - self.holding_since >= self.MAX_HOLD_US):
            self.exiting = True

        if self.order_id is not None:
            return
        if self.inventory:
            # Exits need only the liquidation side and ignore entry spread/flow.
            if self.exiting and exit_price is not None and now >= self.retry_at:
                side = Side.SELL if self.inventory > 0 else Side.BUY
                self.retry_at = now + self.EXIT_RETRY_US
                self._send(side, exit_price, abs(self.inventory))
            return
        if self.halted or now < self.cooldown_until:
            self.signal = None
            return
        if not bids or not asks:
            return
        bid, ask = bids[0].price, asks[0].price
        if ask <= bid or ask - bid > self.MAX_SPREAD:
            self.signal = None
            return
        mid = (bid + ask) / 2
        flow = sum((1 if t.book_side == 'ask' else -1) * t.quantity
                   for t in trades if t.taker_owner == 'market' and t.maker_owner == 'market')
        if self.signal is not None and now - self.signal[1] > self.SIGNAL_TTL_US:
            self.signal = None
        if flow:
            direction = 1 if flow > 0 else -1
            if self.signal is None or self.signal[0] != direction:
                self.signal = (direction, now, mid)
        if self.signal is None:
            return
        direction, started, reference_mid = self.signal
        if now - started < self.CONFIRM_US or direction * (mid - reference_mid) < 1:
            return
        side = Side.BUY if direction > 0 else Side.SELL
        touch = asks if direction > 0 else bids
        price = touch[0].price
        touch_size = sum(o.quantity for o in touch if o.price == price)
        quantity = min(self.LOT, self.LIMIT, max(1, touch_size // 4))
        self.signal = None
        self.entry_cash = self.cash
        self._send(side, price, quantity)

    def on_private_order_update(self, event: PrivateOrderEvent) -> None:
        if event.order_id != self.order_id:
            return
        if event.status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            sign = 1 if self.order_side == Side.BUY else -1
            if self.inventory == 0:
                self.holding_since = event.timestamp_us
            self.inventory += sign * event.filled_quantity
            self.cash -= sign * event.filled_quantity * event.fill_price
            if self.inventory == 0:
                self.holding_since = None
                self.exiting = False
                self.cooldown_until = event.timestamp_us + self.COOLDOWN_US
                self.signal = None
        if event.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED):
            self.order_id = None
            self.order_side = None
