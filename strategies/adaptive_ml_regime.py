"""VARIANT combo: regime variant + passive fade in choppy volatility (switch off, no crash regime):
the inventory centre leans AGAINST a FADE_THRESHOLD move over FADE_LOOKBACK seconds, built passively.

VARIANT regime: the maker's inventory centre moves to -REGIME_CENTER in a crash (price >= CRASH_DROP
below its 15-min high) and to +REGIME_CENTER in the recovery after it (>= RECOVERY_RISE off the crash low);
positions are built passively by the maker (no IOC), regimes held >= 2 min, exit to neutral on a
REGIME_EXIT give-back, never flipping directly.

adaptive_maker with an ML volatility forecast driving the inventory limit.

The volatility switch of `adaptive_maker` reacts to a lagging EWMA of 1 s mid
returns, so it steps aside only after a jump. Here a ridge model forecasts
the next 10 s realized volatility from per-second book features (spread,
event rate, orders and quantity at the touch, trade flow, realized vol over
5/10/30/120 s, recent jumps); its weights are embedded below. The dominant
inputs are the 5 s mean spread and event rate (the book widens and gets busy
before jumps) - realized vol itself carries almost no weight.

Measured on round2_public (model trained on the first 50 min only):
    adaptive_maker                second half (held out) 53,275 | full 110,448
    21-feature model, 1.3/2.0                            71,489 |      151,434
    36-feature model, 1.4/2.2 (shipped)                  76,716 |      159,974
Forecast R^2 for next-10 s vol on the held-out half: EWMA 0.18, ridge 0.42 (21 f), 0.48 (36 f).
The shipped weights are refit on the whole of round2_public.

Original adaptive_maker notes:

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
3. Volatility switch (replaced in this file by the ridge forecast). EWMA of squared 1-second mid
   returns; the inventory limit scales linearly from LIMIT at VOL_LO to 0 at
   VOL_HI, so in a crash the strategy only unwinds and stops adding. round1
   (1 s vol ~0.9) never triggers it; round2 (crashes at 4-8 ticks/s) is
   where all the losses came from.
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
FORECAST_LO = 1.4  # ticks/s forecast: full limit at or below this
FORECAST_HI = 2.2  # ticks/s forecast: zero limit (unwind only) at or above this

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
BANDIT = None  # None = fixed LO/HI ramp; 'greedy' | 'thompson' | 'kelly' | 'thompson_kelly' = online per-bucket sizing
BUCKET_EDGES = (1.0, 1.4, 1.8, 2.2, 3.0)  # forecast bucket boundaries (ticks/s)
PRIOR_MEANS = (40.0, 33.0, 26.0, -35.0, -360.0, -300.0)  # PnL per second at full size per bucket (round2 first half)
PRIOR_STDS = (135.0, 103.0, 124.0, 152.0, 609.0, 534.0)  # per-second PnL std per bucket (round2 first half)
PRIOR_WEIGHT = 300.0  # pseudo-seconds of confidence in the prior means
JUMP_CONTEXT = False  # bandit cells = forecast bucket x seconds since the last >= JUMP_TICKS 1 s move
JUMP_TICKS = 10.0
JUMP_EDGES = (10, 60, 300)  # seconds-since-jump bucket boundaries
KELLY_SCALE = 30.0  # PnL/s at which the 'kelly' policies reach full size
STEP_CLIP = 3000.0  # clip of one second's normalised PnL contribution
VACUUM_SPREAD = 4  # market spread >= this: quote full size just inside the wide spread on both sides
VACUUM_OFFSET = 1  # ticks inside the far touch for vacuum quotes
VACUUM_FULL = False  # vacuum quotes use the full limit (ignore the volatility forecast)
REGIME = True  # shift the maker's inventory centre short in a crash and long in the recovery after it
REGIME_WINDOW = 900  # seconds of history for the rolling high/low
CRASH_DROP = 150.0  # ticks below the rolling high that define a crash
RECOVERY_RISE = 80.0  # ticks above the crash low that define a recovery (only within RECOVERY_WINDOW after a crash)
REGIME_EXIT = 60.0  # ticks the price must give back (from the extreme since entry) to leave a regime
RECOVERY_WINDOW = 1800  # seconds after a crash during which a recovery can be traded
REGIME_MIN_HOLD = 120  # seconds a regime is held at least
FADE_SIZE = 50  # lots: in choppy volatility (switch off, no crash regime) lean the inventory centre AGAINST big moves
FADE_LOOKBACK = 300  # seconds over which the move is measured for the fade
FADE_THRESHOLD = 60.0  # ticks of move needed to fade it
REGIME_CENTER = 100  # lots: inventory centre in a regime (short in a crash, long in a recovery)
RESCUE_SLIP = 2  # ticks through the touch for the over-limit rescue IOC

# order record fields
_SIDE, _PX, _REM, _CXL, _SEQ, _PMOD, _ACC = range(7)


class AdaptiveMakerMLStrategy(BaseStrategy):
    """adaptive_maker with the inventory limit driven by a ridge volatility forecast."""

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
            bandit: str | None = BANDIT,
            bucket_edges: tuple = BUCKET_EDGES,
            prior_means: tuple = PRIOR_MEANS,
            prior_stds: tuple = PRIOR_STDS,
            prior_weight: float = PRIOR_WEIGHT,
            kelly_scale: float = KELLY_SCALE,
            jump_context: bool = JUMP_CONTEXT,
            vacuum_spread: int | None = VACUUM_SPREAD,
            vacuum_offset: int = VACUUM_OFFSET,
            vacuum_full: bool = VACUUM_FULL,
            regime: bool = REGIME,
            crash_drop: float = CRASH_DROP,
            recovery_rise: float | None = RECOVERY_RISE,
            regime_exit: float = REGIME_EXIT,
            regime_center: int = REGIME_CENTER,
            regime_window: int = REGIME_WINDOW,
            fade_size: int = FADE_SIZE,
            fade_lookback: int = FADE_LOOKBACK,
            fade_threshold: float = FADE_THRESHOLD,
            prior_counts: tuple | None = None,
    ) -> None:
        super().__init__()
        self._limit = limit
        self._imb_gate = imb_gate
        self._flip_gate = flip_gate
        self._flip_keep = flip_keep
        self._f_lo = forecast_lo
        self._f_hi = forecast_hi
        self._vw = vol_weights
        self._vb = vol_bias
        self._bandit = bandit
        self._edges = bucket_edges
        self._kelly = kelly_scale
        weights = [prior_weight] * len(prior_means) if prior_counts is None else [
            max(5.0, min(prior_weight, c)) for c in prior_counts]
        self._b_n = list(weights)
        self._b_sum = [m * w for m, w in zip(prior_means, weights)]
        self._b_sq = [(sd * sd + m * m) * w for m, sd, w in zip(prior_means, prior_stds, weights)]
        self._jump_context = jump_context
        self._vac = vacuum_spread
        self._vac_off = vacuum_offset
        self._vac_full = vacuum_full
        self._regime = regime
        self._crash_drop = crash_drop
        self._rec_rise = recovery_rise
        self._reg_exit = regime_exit
        self._reg_center = regime_center
        self._reg_window = regime_window
        self._fade_size = fade_size
        self._fade_lb = fade_lookback
        self._fade_thr = fade_threshold
        self._mids: list = []
        self._state = 0  # 0 neutral, -1 crash (centre short), +1 recovery (centre long)
        self._state_since = 0
        self._extreme = 0.0  # low since crash entry / high since recovery entry
        self._crash_low: float | None = None
        self._crash_end = -10**9
        self._center = 0
        self._seconds = 0
        self._since_reset = 10**9  # seconds since the last regime exit (limits the rolling-high lookback)
        self._sec_count = 0
        self._last_jump = -10**9
        self._bucket: int | None = None
        self._frac = 1.0
        self._cash = 0.0
        self._last_mtm: float | None = None
        self._rng = 12345  # deterministic LCG state for Thompson draws
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
        self._best = (bid_px, ask_px)
        self._update_volatility(
            snapshot.timestamp_us, bid_px, ask_px, min(bid_qty, ask_qty), min(bid_n, ask_n), trades
        )

        imbalance = (bid_qty - ask_qty) / (bid_qty + ask_qty)
        limit = self._eff_limit
        vacuum = self._vac is not None and ask_px - bid_px >= self._vac
        if vacuum and self._vac_full:
            limit = self._limit
        for side, own_imb in ((Side.BUY, imbalance), (Side.SELL, -imbalance)):
            step = -1 if side == Side.BUY else 1
            touch = best[side][0]
            if vacuum:
                touch = touch - step * self._vac_off  # step inside the wide spread
            deep = touch + step
            if side == Side.BUY:
                adding = self._inventory >= self._center
                room = max(0, self._center + limit - self._inventory, self._center - self._inventory)
                room = min(room, self._limit - self._inventory)
            else:
                adding = self._inventory <= self._center
                room = max(0, self._inventory - (self._center - limit), self._inventory - self._center)
                room = min(room, self._limit + self._inventory)
            if adding:
                gated = (self._imb_gate is not None and own_imb < self._imb_gate)
                touch_qty = 0 if gated else room
            elif self._flip_gate is not None and own_imb < self._flip_gate:
                touch_qty = min(room, abs(self._inventory - self._center) + self._flip_keep)
            else:
                touch_qty = room
            self._reconcile(side, touch, {touch: touch_qty, deep: room - touch_qty})

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
            if self._bandit is not None:
                self._bandit_step(forecast, mid)
            else:
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

    def _gauss(self) -> float:
        """Standard normal draw from a deterministic LCG (Box-Muller)."""
        draws = []
        for _ in range(2):
            self._rng = (self._rng * 6364136223846793005 + 1442695040888963407) % (1 << 64)
            draws.append(((self._rng >> 11) + 0.5) / (1 << 53))
        return math.sqrt(-2 * math.log(draws[0])) * math.cos(2 * math.pi * draws[1])

    def _bandit_step(self, forecast: float, mid: float) -> None:
        """Credit last second's PnL to its bucket, then size this second from the new bucket's estimate."""
        mtm = self._cash + self._inventory * mid
        if self._bucket is not None and self._last_mtm is not None and self._frac > 0:
            step = max(-STEP_CLIP, min(STEP_CLIP, (mtm - self._last_mtm) / self._frac))
            b = self._bucket
            self._b_n[b] += 1
            self._b_sum[b] += step
            self._b_sq[b] += step * step
        self._last_mtm = mtm
        b = 0
        while b < len(self._edges) and forecast >= self._edges[b]:
            b += 1
        if self._jump_context:
            since = self._sec_count - self._last_jump
            j = 0
            while j < len(JUMP_EDGES) and since > JUMP_EDGES[j]:
                j += 1
            b = b * (len(JUMP_EDGES) + 1) + j
        self._bucket = b
        n = self._b_n[b]
        mean = self._b_sum[b] / n
        if self._bandit in ('thompson', 'thompson_kelly'):
            var = max(self._b_sq[b] / n - mean * mean, 1.0)
            mean += self._gauss() * math.sqrt(var / n)
        if self._bandit in ('kelly', 'thompson_kelly'):
            self._frac = max(0.0, min(1.0, mean / self._kelly))
        else:
            self._frac = 1.0 if mean > 0 else 0.0
        self._eff_limit = int(self._limit * self._frac)

    def _close_second(self) -> None:
        spread_sum, spread_max, depth_sum, count_sum, traded, n_trades, events, mid = self._acc
        events = max(events, 1)
        ret = 0.0 if self._prev_mid is None else mid - self._prev_mid
        self._prev_mid = mid
        self._mids.append(mid)
        if len(self._mids) > self._reg_window:
            del self._mids[0]
        if self._regime:
            self._update_regime(mid)
        self._ewm10 += (1 - 0.5 ** 0.1) * (ret * ret - self._ewm10)
        self._sec_count += 1
        if abs(ret) >= JUMP_TICKS:
            self._last_jump = self._sec_count
        self._hist.append((ret, spread_sum / events, spread_max, depth_sum / events, count_sum / events, traded, n_trades, events))
        if len(self._hist) > 120:
            del self._hist[0]

    def _update_regime(self, mid: float) -> None:
        """Crash / recovery state machine on per-second mids; sets the inventory centre."""
        n = len(self._mids)  # seconds of history (capped at the window)
        self._state_since += 1
        self._since_reset += 1
        look = min(len(self._mids), self._since_reset)
        hi = max(self._mids[-look:]) if look > 0 else mid
        if self._state == 0:
            if hi - mid >= self._crash_drop:
                self._state, self._state_since, self._extreme = -1, 0, mid
            elif (self._rec_rise is not None and self._crash_low is not None and self._crash_end > -10**8
                  and self._sec_count_since_crash() <= RECOVERY_WINDOW and mid - self._crash_low >= self._rec_rise):
                self._state, self._state_since, self._extreme = 1, 0, mid
        elif self._state == -1:
            self._extreme = min(self._extreme, mid)
            self._crash_low = self._extreme if self._crash_low is None else min(self._crash_low, self._extreme)
            if self._state_since >= REGIME_MIN_HOLD and mid - self._extreme >= self._reg_exit:
                self._state, self._state_since = 0, 0
                self._crash_end = self._seconds
                self._since_reset = 0
        else:
            self._extreme = max(self._extreme, mid)
            if self._state_since >= REGIME_MIN_HOLD and self._extreme - mid >= self._reg_exit:
                self._state, self._state_since = 0, 0
                self._crash_low = None  # one recovery per crash
                self._since_reset = 0
        self._center = self._state * self._reg_center
        if self._state == 0 and self._fade_size and self._eff_limit == 0 and len(self._mids) > self._fade_lb:
            move = mid - self._mids[-1 - self._fade_lb]
            if abs(move) >= self._fade_thr:
                self._center = -self._fade_size if move > 0 else self._fade_size
        self._seconds += 1

    def _sec_count_since_crash(self) -> int:
        return self._seconds - self._crash_end

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
                self._cash -= sign * event.filled_quantity * (event.fill_price or 0)
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
            self._cash -= signed * (event.fill_price or 0)
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
