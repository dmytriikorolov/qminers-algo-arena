"""Execution-aware fixed-depth experiments with the official inventory limits."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from simulator.simulator import ExchangeSimulator, SimulationConfig
from simulator.models import OrderBookSnapshot, BookOrderView
from strategies.full_two_sided import FullTwoSidedStrategy


class DepthMaker(FullTwoSidedStrategy):
    def __init__(self, offset):
        super().__init__()
        self.offset = offset

    def on_order_book_change(self, snapshot, trades):
        def shifted(orders, direction):
            return [BookOrderView(o.order_id, o.side, max(1, o.price + direction * self.offset), o.quantity, o.owner)
                    for o in orders]
        super().on_order_book_change(OrderBookSnapshot(snapshot.timestamp_us,
            shifted(snapshot.bids, -1), shifted(snapshot.asks, 1)), trades)


if __name__ == '__main__':
    offset = int(sys.argv[1])
    engine = ExchangeSimulator(DepthMaker(offset), SimulationConfig(order_accept_delay_ms=5,
        max_position=100, max_potential_position=1000, position_breach_penalty_per_second=10000))
    result = engine.run(ROOT / 'data/round3_public.csv')
    output = ROOT / 'logs/round3_quote_search'
    output.mkdir(parents=True, exist_ok=True)
    (output / f'offset_{offset}.json').write_text(json.dumps(result.model_dump(), indent=2))
    print(offset, result.model_dump(), flush=True)
