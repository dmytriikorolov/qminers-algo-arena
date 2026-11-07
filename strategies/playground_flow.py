"""Bounded trade-flow follower for the official 5 ms exchange."""

from simulator.models import OrderBookSnapshot, OrderRequest, OrderStatus, OrderType, PrivateOrderEvent, Side, Trade
from simulator.strategy import BaseStrategy


class PlaygroundFlowStrategy(BaseStrategy):
    LOT = 20
    LIMIT = 20
    MAX_SPREAD = 4

    def __init__(self) -> None:
        super().__init__()
        self.inventory = 0
        self.order_id = None
        self.order_side = None
        self.last_fill_side = None

    def on_order_book_change(self, snapshot: OrderBookSnapshot, trades: list[Trade]) -> None:
        if self.order_id is not None:
            return
        bids = [o for o in snapshot.bids if o.owner == 'market']
        asks = [o for o in snapshot.asks if o.owner == 'market']
        if not bids or not asks:
            return
        bid, ask = bids[0].price, asks[0].price
        if ask <= bid or ask - bid > self.MAX_SPREAD:
            return
        flow = sum((1 if t.book_side == 'ask' else -1) * t.quantity
                   for t in trades if t.taker_owner == 'market' and t.maker_owner == 'market')
        if flow == 0:
            return
        side = Side.BUY if flow > 0 else Side.SELL
        if side == self.last_fill_side:
            return
        room = self.LIMIT - self.inventory if side == Side.BUY else self.LIMIT + self.inventory
        quantity = min(self.LOT, room)
        if quantity <= 0:
            return
        self.order_side = side
        self.order_id = self.send_order(OrderRequest(
            side=side, price=ask if side == Side.BUY else bid,
            quantity=quantity, order_type=OrderType.IOC))

    def on_private_order_update(self, event: PrivateOrderEvent) -> None:
        if event.order_id != self.order_id:
            return
        if event.status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            self.inventory += event.filled_quantity * (1 if self.order_side == Side.BUY else -1)
            self.last_fill_side = self.order_side
        if event.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED):
            self.order_id = None
            self.order_side = None
