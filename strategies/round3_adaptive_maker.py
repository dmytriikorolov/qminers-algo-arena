"""Volatility-sized market making with a bounded passive reversal target.

The volatility coefficients were fitted on public round 2. The inventory
center fades the last 30 completed one-second returns and shrinks as the
forecast rises. No runtime data files, pretrained round 3 weights or future
observations are used. Public replay selection is not a holdout result.

Fast requoting can briefly exceed the inventory limit during cancel races;
strict_exposure=True waits for acknowledgments instead, at a PnL cost.
"""

from __future__ import annotations

import math

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
FORECAST_LO = 2.0  # ticks/s forecast: full limit at or below this
FORECAST_HI = 3.0  # ticks/s forecast: move only toward the inventory target above this

# Ridge on log1p(features) -> log1p(next-10 s realized vol), fit on round2_public.
# Feature order: rv5 rv10 rv30 rv120 ewm10; then (5 s mean, 60 s mean) of
# spread, max spread, min(L1 qty), min(L1 order count), traded qty, trade
# count, event count; then |last 1 s return|, max |1 s return| over 60 s;
# then (last 1 s, 2 s mean) of the same seven per-second stats; then rv2.
VOL_WEIGHTS = (
    0.030272, 0.071227, -0.030872, -0.033701, 0.023996,
    0.449146, 0.110180, -0.200480, 0.044494, 0.018999, 0.113348, -0.244893, -0.276312,
    -0.032322, 0.004853, -0.004713, -0.048390, 0.847368, -0.015825,
    -0.012012, -0.030385,
    1.058262, 0.574015, -0.065912, 0.007384, -0.020314, 0.010959, -0.069470, -0.006948,
    0.026800, -0.006000, -0.023349, -0.040489, -0.181504, 0.441253,
    0.031795,
)
VOL_BIAS = -5.972697
VACUUM_SPREAD = 4  # market spread >= this: quote full size just inside the wide spread on both sides
VACUUM_OFFSET = 1  # ticks inside the far touch for vacuum quotes
VACUUM_FULL = False  # vacuum quotes use the full limit (ignore the volatility forecast)
VOLATILITY_QUOTES = True  # elevated forecast also controls prices and flip exposure
RISK_HORIZON_SECONDS = 0.25  # heuristic quote-risk horizon; not a trained markout model
MAX_RISK_OFFSET = 3  # cap additional distance from the market touch
SHOCK_COOLDOWN_MS = 1000  # pause inventory growth after an intrasecond jump; 0 disables
SHOCK_TICKS = 4.0  # minimum midpoint jump from the last completed second
SHOCK_MULTIPLIER = 2.0  # also require jump >= this times the predicted one-second RMS
RESCUE_SLIP = 2  # ticks through the touch for the over-limit rescue IOC

# order record fields
_SIDE, _PX, _REM, _CXL, _SEQ, _PMOD, _ACC = range(7)


class Round3AdaptiveMaker(BaseStrategy):
    """Quote around a causal reversal target, inside the hard inventory bounds."""

    def __init__(
        self,
        limit: int = LIMIT,
        imb_gate: float | None = IMB_GATE,
        flip_gate: float | None = FLIP_GATE,
        flip_keep: int = FLIP_KEEP,
        forecast_lo: float | None = FORECAST_LO,
        forecast_hi: float = FORECAST_HI,
        vol_weights: tuple = VOL_WEIGHTS,
        vol_bias: float = VOL_BIAS,
        vacuum_spread: int | None = VACUUM_SPREAD,
        vacuum_offset: int = VACUUM_OFFSET,
        vacuum_full: bool = VACUUM_FULL,
        volatility_quotes: bool = VOLATILITY_QUOTES,
        risk_horizon_seconds: float = RISK_HORIZON_SECONDS,
        max_risk_offset: int = MAX_RISK_OFFSET,
        shock_cooldown_ms: float = SHOCK_COOLDOWN_MS,
        shock_ticks: float = SHOCK_TICKS,
        shock_multiplier: float = SHOCK_MULTIPLIER,
        fade_strength: float = 8.0,
        fade_limit: int = 40,
        fade_risk: float = 2.0,
        strict_exposure: bool = False,
    ) -> None:
        super().__init__()
        for name, value in (('risk_horizon_seconds', risk_horizon_seconds),
                            ('shock_ticks', shock_ticks), ('shock_multiplier', shock_multiplier)):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        if not isinstance(max_risk_offset, int) or max_risk_offset < 0:
            raise ValueError('max_risk_offset must be a nonnegative integer')
        if not math.isfinite(shock_cooldown_ms) or shock_cooldown_ms < 0:
            raise ValueError('shock_cooldown_ms must be finite and nonnegative')
        if not math.isfinite(fade_strength) or fade_strength < 0:
            raise ValueError('fade_strength must be finite and nonnegative')
        if not isinstance(fade_limit, int) or not 0 <= fade_limit <= limit:
            raise ValueError('fade_limit must be between zero and the inventory limit')
        if not math.isfinite(fade_risk) or fade_risk <= 0:
            raise ValueError('fade_risk must be finite and positive')
        self._fade_strength = fade_strength
        self._fade_limit = fade_limit
        self._fade_risk = fade_risk
        self._strict_exposure = strict_exposure
        self._center = 0
        self._limit = limit
        self._imb_gate = imb_gate
        self._flip_gate = flip_gate
        self._flip_keep = flip_keep
        self._f_lo = forecast_lo
        self._f_hi = forecast_hi
        self._vw = vol_weights
        self._vb = vol_bias
        self._vac = vacuum_spread
        self._vac_off = vacuum_offset
        self._vac_full = vacuum_full
        self._volatility_quotes = volatility_quotes
        self._risk_horizon = risk_horizon_seconds
        self._max_risk_offset = max_risk_offset
        self._shock_cooldown_us = int(shock_cooldown_ms * 1000)
        self._shock_ticks, self._shock_multiplier = shock_ticks, shock_multiplier
        self._shock_until_us = 0
        self.last_forecast = 0.0
        self.shock_events = self.risk_quote_updates = self.flip_protection_updates = 0
        self.max_abs_inventory = 0
        self._sec: int | None = None
        self._acc: list = []  # current second: spread sum, spread max, depth sum, count sum, traded, trades, events, mid
        self._hist: list = []  # closed seconds (newest last, max 120): r, spread, spmax, depth, count, traded, trades, events
        self._prev_mid: float | None = None
        self._ewm10 = 0.0
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
            count = 0
            for order in book:
                if order.owner != 'market':
                    continue
                if price is None:
                    price = order.price
                elif order.price != price:
                    break
                quantity += order.quantity
                count += 1
            if price is None:
                return
            best[side] = (price, quantity, count)
        (bid_px, bid_qty, bid_n), (ask_px, ask_qty, ask_n) = best[Side.BUY], best[Side.SELL]
        if not 0 < bid_px < ask_px:
            return
        self._best = (bid_px, ask_px)
        previous_second = self._sec
        self._update_volatility(
            snapshot.timestamp_us, bid_px, ask_px, min(bid_qty, ask_qty), min(bid_n, ask_n), trades
        )

        if self._sec != previous_second:
            self._update_center()

        imbalance = (bid_qty - ask_qty) / (bid_qty + ask_qty)
        limit = self._eff_limit
        vacuum = self._vac is not None and ask_px - bid_px >= self._vac
        if vacuum and self._vac_full:
            limit = self._limit
        if self._shock_cooldown_us and self._prev_mid is not None:
            threshold = max(self._shock_ticks, self._shock_multiplier * max(0.0, self.last_forecast))
            if abs((bid_px + ask_px) / 2 - self._prev_mid) >= threshold:
                if snapshot.timestamp_us >= self._shock_until_us:
                    self.shock_events += 1
                self._shock_until_us = snapshot.timestamp_us + self._shock_cooldown_us
        if snapshot.timestamp_us < self._shock_until_us:
            limit = 0  # only move toward the risk-scaled inventory target
        for side, own_imb in ((Side.BUY, imbalance), (Side.SELL, -imbalance)):
            touch, want = self._quote_targets(side, bid_px, ask_px, own_imb, limit, vacuum)
            self._reconcile(side, touch, want)

    def _update_center(self) -> None:
        if len(self._hist) < 30:
            return
        move = sum(row[0] for row in self._hist[-30:])
        target = max(-self._fade_limit, min(self._fade_limit, -self._fade_strength * move))
        risk_fraction = min(1.0, self._fade_risk / max(0.1, self.last_forecast))
        self._center = round(target * risk_fraction)

    def _quote_targets(self, side, bid_px, ask_px, own_imb, limit, vacuum):
        touch, want = self._centered_quote_targets(side, bid_px, ask_px, own_imb, limit, vacuum)
        sign = 1 if side == Side.BUY else -1
        # Leave race-induced excess to the rescue IOC, without enlarging the
        # passive quote beyond a normal full inventory flip.
        room = min(2 * self._limit, max(0, self._limit - sign * self._inventory))
        targets = {}
        for price, quantity in want.items():
            quantity = min(quantity, room)
            room -= quantity
            if quantity > 0:
                targets[price] = targets.get(price, 0) + quantity
        return touch, targets

    def _centered_quote_targets(self, side, bid_px, ask_px, own_imb, limit, vacuum):
        """Allocate target-seeking/overshoot capacity separately; preserve total per-side room."""
        inventory = self._inventory - self._center
        step = -1 if side == Side.BUY else 1
        market_touch = bid_px if side == Side.BUY else ask_px
        touch = market_touch - step * self._vac_off if vacuum else market_touch
        deep = touch + step
        adding = inventory >= 0 if side == Side.BUY else inventory <= 0
        room = (max(0, limit - inventory, -inventory) if side == Side.BUY
                else max(0, limit + inventory, inventory))
        if adding:
            gated = self._imb_gate is not None and own_imb < self._imb_gate
            touch_qty = 0 if gated else room
        elif self._flip_gate is not None and own_imb < self._flip_gate:
            touch_qty = min(room, abs(inventory) + self._flip_keep)
        else:
            touch_qty = room

        elevated = (self._volatility_quotes and self._f_lo is not None
                    and math.isfinite(self.last_forecast) and self.last_forecast > self._f_lo)
        if not elevated:
            return touch, {touch: touch_qty, deep: room - touch_qty}

        spread = ask_px - bid_px
        risk = max(0.0, self.last_forecast) * math.sqrt(self._risk_horizon)
        offset = min(self._max_risk_offset, max(0, math.ceil(risk - spread / 2)))
        risk_price = max(1, market_touch + step * offset)
        if adding:
            original = deep if touch_qty == 0 else touch
            target = min(original, risk_price) if side == Side.BUY else max(original, risk_price)
            target = max(1, target)
            # In a wide spread, do not improve the price for new exposure when
            # the forecast is elevated; keep improvement for flattening instead.
            self.risk_quote_updates += int(room > 0 and target != original)
            return target, {target: room}

        flatten = min(room, abs(inventory))
        # At narrow spreads retain a shrinking part of flip capacity at touch.
        # At wide spreads, all flip capacity sits behind the flattening quote.
        flip_at_touch = 0 if vacuum else int(self._flip_keep * min(1.0, limit / self._limit))
        protected_touch_qty = min(touch_qty, flatten + flip_at_touch)
        deep = min(deep, risk_price) if side == Side.BUY else max(deep, risk_price)
        deep = max(1, deep)
        self.flip_protection_updates += int(protected_touch_qty < touch_qty)
        if deep == touch:
            return touch, {touch: room}
        return touch, {touch: protected_touch_qty, deep: room - protected_touch_qty}

    def _update_volatility(self, timestamp_us: int, bid_px: int, ask_px: int, depth: int, count: int, trades: list) -> None:
        """Aggregate per-second features; at each new second, forecast vol and rescale the limit."""
        if self._f_lo is None:
            return
        sec = timestamp_us // 1_000_000
        spread = ask_px - bid_px
        mid = (bid_px + ask_px) / 2
        if self._sec is None:
            self._sec, self._acc = sec, [0, 0, 0, 0, 0, 0, 0, mid]
        elif sec > self._sec:
            self._close_second()
            for _ in range(min(sec - self._sec - 1, 120)):  # silent seconds repeat the last record
                self._close_second()
            self._sec, self._acc = sec, [0, 0, 0, 0, 0, 0, 0, mid]
            forecast = self._forecast()
            self.last_forecast = forecast
            if forecast <= self._f_lo:
                fraction = 1.0
            elif forecast >= self._f_hi:
                fraction = 0.0
            else:
                fraction = (self._f_hi - forecast) / (self._f_hi - self._f_lo)
            self._eff_limit = int(self._limit * fraction)
        acc = self._acc
        acc[0] += spread
        acc[1] = max(acc[1], spread)
        acc[2] += depth
        acc[3] += count
        acc[4] += sum(trade.quantity for trade in trades)
        acc[5] += len(trades)
        acc[6] += 1
        acc[7] = mid



    def _close_second(self) -> None:
        spread_sum, spread_max, depth_sum, count_sum, traded, n_trades, events, mid = self._acc
        events = max(events, 1)
        ret = 0.0 if self._prev_mid is None else mid - self._prev_mid
        self._prev_mid = mid
        self._ewm10 += (1 - 0.5 ** 0.1) * (ret * ret - self._ewm10)
        self._hist.append((ret, spread_sum / events, spread_max, depth_sum / events, count_sum / events, traded, n_trades, events))
        if len(self._hist) > 120:
            del self._hist[0]

    def _forecast(self) -> float:
        hist = self._hist

        def mean(col: int, n: int) -> float:
            window = hist[-n:]
            return sum(row[col] for row in window) / len(window)

        def realized(n: int) -> float:
            window = hist[-n:]
            return (sum(row[0] * row[0] for row in window) / len(window)) ** 0.5

        features = [realized(5), realized(10), realized(30), realized(120), self._ewm10**0.5]
        for col in range(1, 8):
            features += [mean(col, 5), mean(col, 60)]
        features += [abs(hist[-1][0]), max(abs(row[0]) for row in hist[-60:])]
        if len(self._vw) > len(features):  # extended model: last-second and last-2-second features
            for col in range(1, 8):
                features += [hist[-1][col], mean(col, 2)]
            features.append(realized(2))
        logs = [math.log1p(max(0.0, value)) for value in features]
        z = self._vb
        for weight, value in zip(self._vw, logs):
            z += weight * value
        return math.expm1(min(z, 20.0))

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
            if o[_SIDE] == side and (self._strict_exposure
                or not (o[_CXL] and step * (touch - o[_PX]) > 0))
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

        # Allow a wider rescue during elevated volatility.
        dynamic_slip = max(RESCUE_SLIP, int(self.last_forecast * self._risk_horizon * 3))

        if self._inventory > 0:
            price = max(1, self._best[0] - dynamic_slip)
            order_id = self.send_order(OrderRequest(side=Side.SELL, price=price, quantity=excess, order_type=OrderType.IOC))
            self._iocs[order_id] = -excess
        else:
            price = self._best[1] + dynamic_slip
            order_id = self.send_order(OrderRequest(side=Side.BUY, price=price, quantity=excess, order_type=OrderType.IOC))
            self._iocs[order_id] = excess

    def on_private_order_update(self, event: PrivateOrderEvent) -> None:
        """Track inventory, remaining quantities, modifies and terminal states."""
        status = event.status
        if event.order_id in self._iocs:
            if status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
                sign = 1 if self._iocs[event.order_id] > 0 else -1
                self._inventory += sign * event.filled_quantity
                self.max_abs_inventory = max(self.max_abs_inventory, abs(self._inventory))
                self._iocs[event.order_id] = sign * event.remaining_quantity
            if status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED):
                del self._iocs[event.order_id]
            return

        order = self._orders.get(event.order_id)
        if order is None:
            return
        if status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            signed = event.filled_quantity if order[_SIDE] == Side.BUY else -event.filled_quantity
            self._inventory += signed
            self.max_abs_inventory = max(self.max_abs_inventory, abs(self._inventory))
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
