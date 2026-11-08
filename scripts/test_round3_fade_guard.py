"""Round 3-only test of a risk cap on the best runner's fade inventory center."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from strategies.adaptive_ml_regime import AdaptiveMakerMLStrategy
from simulator.simulator import ExchangeSimulator, SimulationConfig


class GuardedMaker(AdaptiveMakerMLStrategy):
    def __init__(self, cap):
        super().__init__(crash_drop=1e9, recovery_rise=None)
        self.cap = cap
        self.forecast = 0.0

    def _update_volatility(self, *args):
        previous_second = self._sec
        super()._update_volatility(*args)
        if self._hist and self._sec != previous_second:
            self.forecast = self._forecast()
        if self.cap > 0 and self.forecast >= self.cap:
            self._center = 0
        if self.cap < 0 and self._prev_mid is not None:
            mid = (args[1] + args[2]) / 2
            if abs(mid - self._prev_mid) >= max(-self.cap, 2 * self.forecast):
                self._eff_limit = 0
                self._center = 0


if __name__ == '__main__':
    cap = float(sys.argv[1])
    engine = ExchangeSimulator(GuardedMaker(cap), SimulationConfig(order_accept_delay_ms=5,
        max_position=100, max_potential_position=1000, position_breach_penalty_per_second=10000))
    result = engine.run(ROOT / 'data/round3_public.csv')
    points = engine.pnl_curve(result.pnl)
    first = next(p for t,p in reversed(points) if t <= 3000000000)
    peak = dd = 0
    for _, p in points:
        peak = max(peak,p)
        dd = max(dd,peak-p)
    out = ROOT / 'logs/round3_best_audit'
    out.mkdir(parents=True, exist_ok=True)
    record = {**result.model_dump(),'fade_risk_cap':cap,'first_half':first,'second_half':result.pnl-first,'max_drawdown':dd}
    (out / f'guard_{cap}.json').write_text(json.dumps(record,indent=2))
    print(record,flush=True)
