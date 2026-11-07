"""Small reproducible sweep using the untouched official exchange and CLI limits."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

from simulator.main import load_strategy_from_file
from simulator.models import OrderStatus
from simulator.simulator import ExchangeSimulator, SimulationConfig


def run(strategy_path, data_path, parameters, output, cutoff):
    strategy = load_strategy_from_file(strategy_path)
    for name, value in parameters.items():
        setattr(strategy, name, value)
    statuses = Counter()
    max_inventory = 0
    max_reserved = 0
    match_count = 0
    first_fill_latency = None
    original_update = strategy.on_private_order_update
    simulator = ExchangeSimulator(strategy, SimulationConfig(
        public_depth=20, max_position=100, max_potential_position=1000,
        position_breach_penalty_per_second=10_000, order_accept_delay_ms=5))

    def observe(event):
        nonlocal max_inventory, max_reserved, match_count, first_fill_latency
        statuses[event.status.value] += 1
        if event.status in (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED):
            match_count += 1
        original_update(event)
        max_inventory = max(max_inventory, abs(simulator._inventory))

    strategy.on_private_order_update = observe
    original_submit = simulator.submit_order
    sent = {}

    def submit(request):
        nonlocal max_reserved
        order_id = original_submit(request)
        sent[order_id] = simulator.current_ts_us
        # Includes resting and all submitted, still-unaccepted orders.
        for side in (request.side, request.side.opposite):
            reserved = simulator.book.resting_user_quantity(side)
            reserved += sum(item.request.quantity for item in simulator._pending
                            if hasattr(item, 'request') and item.request.side == side)
            potential = simulator._inventory + (1 if side.value == 'B' else -1) * reserved
            max_reserved = max(max_reserved, abs(potential))
        return order_id

    # Context is a public engine adapter used only by the research harness.
    strategy._ctx.submit_order = submit
    original_observe = strategy.on_private_order_update

    def with_latency(event):
        nonlocal first_fill_latency
        if event.filled_quantity:
            latency = event.timestamp_us - sent[event.order_id]
            first_fill_latency = latency if first_fill_latency is None else min(first_fill_latency, latency)
        original_observe(event)

    strategy.on_private_order_update = with_latency
    started = time.perf_counter()
    result = simulator.run(data_path)
    points = simulator.pnl_curve(result.pnl)
    start = points[0][0]
    development_pnl = next((pnl for ts, pnl in reversed(points) if ts - start <= cutoff * 1_000_000), 0)
    peak = points[0][1]
    drawdown = 0
    blocks = []
    previous = points[0][1]
    for boundary in (1200, 2400, 3600):
        value = next((pnl for ts, pnl in reversed(points) if ts - start <= boundary * 1_000_000), 0)
        blocks.append(value - previous)
        previous = value
    for _, pnl in points:
        peak = max(peak, pnl)
        drawdown = max(drawdown, peak - pnl)
    record = {
        'strategy': str(strategy_path), 'strategy_sha256': hashlib.sha256(strategy_path.read_bytes()).hexdigest(),
        'data': str(data_path), 'data_sha256': hashlib.sha256(data_path.read_bytes()).hexdigest(),
        'parameters': parameters, 'result': result.model_dump(mode='json'),
        'development_pnl': development_pnl, 'final_20m_pnl': result.pnl - development_pnl,
        'chronological_20m_pnl': blocks, 'max_abs_inventory': max_inventory,
        'max_abs_reserved_position_at_submit': max_reserved,
        'sampled_max_drawdown': drawdown, 'statuses': dict(statuses), 'match_count': match_count,
        'minimum_send_to_fill_us': first_fill_latency, 'submitted': simulator._user_order_seq,
        'seconds': time.perf_counter() - started,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + '\n')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('data/sample.csv'))
    parser.add_argument('--stage', choices=('development', 'frozen'), default='development')
    args = parser.parse_args()
    output = Path('research/playground')
    if args.stage == 'development':
        # Preserve all earlier rows/order IDs. Never slice out a cold-start holdout.
        prefix = Path('logs/playground/development.csv')
        prefix.parent.mkdir(parents=True, exist_ok=True)
        with args.data.open() as source, prefix.open('w') as target:
            target.write(next(source))
            for line in source:
                if float(line.split(',', 1)[0]) > 2400:
                    break
                target.write(line)
        cases = [('official', Path('strategies/trend_follower.py'), {}),
                 ('noop', Path('strategies/template_strategy.py'), {})]
        cases += [(f'flow_lot{lot}', Path('strategies/playground_flow.py'), {'LOT': lot})
                  for lot in (1, 5, 10, 20)]
        cases += [(name, Path('strategies/playground_quotes.py'), settings) for name, settings in (
            ('quotes', {}), ('quotes_no_signal', {'SIGNAL_WEIGHT': 0}),
            ('quotes_no_vol', {'VOL_WEIGHT': 0}), ('quotes_cap5', {'LIMIT': 5}))]
        data = prefix
    else:
        # Freeze the selection in the standalone source before running this stage.
        cases = [('official_full', Path('strategies/trend_follower.py'), {}),
                 ('noop_full', Path('strategies/template_strategy.py'), {}),
                 ('candidate_full', Path('strategies/playground_flow.py'), {}),
                 ('quotes_full', Path('strategies/playground_quotes.py'), {})]
        data = args.data
    for name, path, settings in cases:
        record = run(path, data, settings, output / f'{name}.json', 2400)
        print(name, 'pnl=', record['result']['pnl'], 'max_inventory=', record['max_abs_inventory'],
              'penalty=', record['result']['breach_penalty'], flush=True)


if __name__ == '__main__':
    main()
