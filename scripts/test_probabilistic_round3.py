"""Round 3-only evaluation of causal online directional strategies."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from strategies.probabilistic_reversion import ProbabilisticReversion
from strategies.hmm_liquidity_maker import HMMLiquidityMaker
from simulator.simulator import ExchangeSimulator, SimulationConfig

variants={
    'bayes5':dict(horizon=5),
    'bayes10':dict(horizon=10),
    'fade30':dict(mode='fade',lookback=30),
    'fade10':dict(mode='fade',lookback=10),
    'hmm':dict(power=2),
    'hmm_gate10':dict(cutoff=.1),
    'hmm_gate30':dict(cutoff=.3),
}
if __name__=='__main__':
    name=sys.argv[1]
    strategy=HMMLiquidityMaker(**variants[name]) if name.startswith('hmm') else ProbabilisticReversion(**variants[name])
    engine=ExchangeSimulator(strategy,SimulationConfig(order_accept_delay_ms=5,max_position=100,
        max_potential_position=1000,position_breach_penalty_per_second=10000))
    result=engine.run(ROOT/'data/round3_public.csv')
    points=engine.pnl_curve(result.pnl)
    first=next(p for t,p in reversed(points) if t<=3000000000)
    peak=dd=0
    for _,p in points:
        peak=max(peak,p); dd=max(dd,peak-p)
    record={**result.model_dump(),'first_half':first,'second_half':result.pnl-first,'max_drawdown':dd,
        'learned_states':len(strategy.stats) if hasattr(strategy,'stats') else 2,'parameters':variants[name]}
    out=ROOT/'logs/probabilistic_round3'; out.mkdir(parents=True,exist_ok=True)
    (out/f'{name}.json').write_text(json.dumps(record,indent=2))
    print(name,record,flush=True)
