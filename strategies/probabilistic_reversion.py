"""Online Bayesian directional maker. Learns only from already-observed moves.

Each state combines a recent price displacement with liquidity stress. Beta
posteriors estimate up/down probabilities; conditional return means estimate
the size of the edge. Labels mature after five seconds. No fitted tape weights.
"""
from collections import deque
import math

from simulator.models import OrderRequest, OrderType, OrderStatus, Side
from simulator.strategy import BaseStrategy


class ProbabilisticReversion(BaseStrategy):
    def __init__(self, horizon=5, lookback=30, threshold=0.6, size=50, mode='learned'):
        super().__init__()
        self.horizon, self.lookback = horizon, lookback
        self.threshold, self.size, self.mode = threshold, size, mode
        self.inventory = 0
        self.orders = {}
        self.history = deque()
        self.pending_labels = deque()
        self.stats = {}
        self.second = -1
        self.target = 0
        self.previous_mid = None
        self.variance = 1.0

    def on_order_book_change(self, snapshot, trades):
        bid = next((o.price for o in snapshot.bids if o.owner == 'market'), None)
        ask = next((o.price for o in snapshot.asks if o.owner == 'market'), None)
        if bid is None or ask is None:
            return
        now = snapshot.timestamp_us / 1e6
        mid = (bid + ask) / 2
        second = int(now)
        if second != self.second:
            self.second = second
            if self.previous_mid is not None:
                self.variance = .95*self.variance + .05*(mid-self.previous_mid)**2
            self.previous_mid = mid
            while self.pending_labels and self.pending_labels[0][0] <= now:
                _, key, old_mid = self.pending_labels.popleft()
                state = self.stats.setdefault(key, [2.0, 2.0, 0.0, 0.0])
                change = mid - old_mid
                if change:
                    state[0 if change > 0 else 1] += 1
                state[2] += change
                state[3] += 1
            while len(self.history) > 1 and self.history[1][0] <= now-self.lookback:
                self.history.popleft()
            move = mid-self.history[0][1] if self.history else 0.0
            vol = max(1.0, math.sqrt(self.variance))
            standardized = move / (vol*math.sqrt(self.lookback))
            bucket = max(-3, min(3, int(standardized*2)))
            key = (bucket, int(ask-bid >= 2), int(vol >= 2))
            self.pending_labels.append((now+self.horizon, key, mid))
            self.history.append((now, mid))
            if self.mode == 'fade':
                edge = -move / 5
                enough = abs(move) >= 5
            else:
                up, down, total, n = self.stats.get(key, [2.,2.,0.,0.])
                probability = up/(up+down)
                edge = total/(n+20)
                enough = n >= 30 and abs(probability-.5) >= .05
            self.target = (self.size if edge > self.threshold else -self.size if edge < -self.threshold else 0) if enough else 0
        # Keep all unconfirmed cancels in committed exposure.
        for side, price in ((Side.BUY, bid), (Side.SELL, ask)):
            desired = max(0, self.target-self.inventory) if side == Side.BUY else max(0, self.inventory-self.target)
            for oid, order in self.orders.items():
                if order[0] == side and not order[3] and (order[1] != price or desired == 0):
                    self.cancel_order(oid)
                    order[3] = True
            committed = sum(o[2] for o in self.orders.values() if o[0] == side)
            hard_room = 100-self.inventory if side == Side.BUY else 100+self.inventory
            quantity = min(desired, hard_room)-committed
            if quantity > 0:
                oid = self.send_order(OrderRequest(side=side, price=price, quantity=quantity, order_type=OrderType.LIMIT))
                self.orders[oid] = [side, price, quantity, False]

    def on_private_order_update(self, event):
        order = self.orders.get(event.order_id)
        if order is None:
            return
        if event.filled_quantity:
            self.inventory += event.filled_quantity*(1 if order[0] == Side.BUY else -1)
            order[2] = event.remaining_quantity
        if event.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED):
            del self.orders[event.order_id]
