"""Small, predefined baseline ablations; scores are public-tape research."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from simulator.main import load_strategy_from_file
from simulator.simulator import ExchangeSimulator, SimulationConfig

OPTIONS = {
    'short_shock': {'_shock_cooldown_us': 250000},
    'long_shock': {'_shock_cooldown_us': 2000000},
    'no_vacuum': {'_vac': None},
    'no_flip': {'_flip_keep': 0},
    'more_risk': {'_risk_horizon': 1.0},
    'higher_limit_threshold': {'_f_lo': 1.6, '_f_hi': 2.6},
    'strict_exposure': {},
}

if __name__ == '__main__':
    name = sys.argv[1]
    strategy = load_strategy_from_file(ROOT / 'logs/baseline_research/original.py')
    for key, value in OPTIONS[name].items():
        setattr(strategy, key, value)
    if name == 'strict_exposure':
        # Reuse the same source with pending cancels retained in exposure.
        source = (ROOT / 'logs/baseline_research/original.py').read_text()
        source = source.replace("if o[_SIDE] == side and not (o[_CXL] and step * (touch - o[_PX]) > 0)", "if o[_SIDE] == side")
        path = ROOT / 'logs/baseline_research/strict.py'
        path.write_text(source)
        strategy = load_strategy_from_file(path)
    engine = ExchangeSimulator(strategy, SimulationConfig(order_accept_delay_ms=5, max_position=100,
        max_potential_position=1000, position_breach_penalty_per_second=10000))
    result = engine.run(ROOT / 'data/round3_public.csv')
    points = engine.pnl_curve(result.pnl)
    first = next(p for t, p in reversed(points) if t <= 3000000000)
    record = {**result.model_dump(), 'first_half': first, 'second_half': result.pnl-first,
              'max_drawdown': 0.0}
    peak = 0
    for _, pnl in points:
        peak = max(peak, pnl)
        record['max_drawdown'] = max(record['max_drawdown'], peak-pnl)
    (ROOT / f'logs/baseline_research/{name}.json').write_text(json.dumps(record, indent=2))
    print(name, record, flush=True)
