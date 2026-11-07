"""Untuned synthetic adversarial tapes replayed by the official exchange."""

import argparse
import json
from pathlib import Path
import random
import tempfile

from scripts.playground_experiments import run


def make_tape(regime, seed, cycles=30):
    rng = random.Random(seed)
    rows = ['Time,Operation,OrderId,Side,Volume,Price,Lifespan']
    mid = 10000
    bid_id = ask_id = None
    sequence = 0

    def quote(stamp, center, quantity=50):
        nonlocal bid_id, ask_id, sequence
        if bid_id is not None:
            rows.append(f'{stamp:.6f},Cancel,{bid_id},,,,')
            rows.append(f'{stamp + .000001:.6f},Cancel,{ask_id},,,,')
        sequence += 1
        bid_id, ask_id = f'b{sequence}', f'a{sequence}'
        bid_quantity = 10000 if regime == 'depth_only' else quantity
        ask_quantity = 1 if regime == 'depth_only' else quantity
        rows.append(f'{stamp + .000002:.6f},Insert,{bid_id},B,{bid_quantity},{center - 1},G')
        rows.append(f'{stamp + .000003:.6f},Insert,{ask_id},A,{ask_quantity},{center + 1},G')

    for cycle in range(cycles):
        stamp = cycle * 2
        direction = rng.choice([-1, 1])
        quote(stamp, mid)
        side, price = ('B', mid + 1) if direction > 0 else ('A', mid - 1)
        # Depth imbalance without an executed flow signal must not cause entry.
        if regime != 'depth_only':
            rows.append(f'{stamp + .01:.6f},Insert,t{cycle},{side},1,{price},F')
        quote(stamp + .2, mid + direction * 2)
        if regime == 'continuation':
            end = mid + direction * rng.randint(4, 7)
        elif regime == 'reversal':
            end = mid - direction * rng.randint(2, 7)
        elif regime == 'gap':
            end = mid - direction * rng.randint(30, 60)
        else:
            end = mid + rng.randint(-3, 3)
        quote(stamp + .4, end, quantity=1 if regime == 'thin' else 50)
        quote(stamp + .7, end, quantity=1 if regime == 'thin' else 50)
        quote(stamp + 1.3, end)
        rows.append(f'{stamp + 1.9:.6f},Cancel,heartbeat,,,,')
        mid = end
    return '\n'.join(rows) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', nargs='+', type=int, default=[101, 102, 103, 104])
    args = parser.parse_args()
    records = []
    policies = [
        ('flow20', 'strategies/playground_flow.py', {}),
        ('flow2_control', 'strategies/playground_flow.py', {'LOT': 2, 'LIMIT': 2}),
        ('defensive', 'strategies/defensive_flow.py', {}),
        ('noop', 'strategies/template_strategy.py', {}),
    ]
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        for regime in ('continuation', 'reversal', 'gap', 'thin', 'depth_only'):
            for seed in args.seeds:
                tape = folder / 'tape.csv'
                tape.write_text(make_tape(regime, seed))
                for policy, path, settings in policies:
                    result = run(Path(path), tape, settings, folder / 'result.json', 40)
                    records.append({
                        'regime': regime, 'seed': seed, 'policy': policy,
                        'parameters': settings, 'data_sha256': result['data_sha256'],
                        'strategy_sha256': result['strategy_sha256'],
                        'pnl': result['result']['pnl'], 'penalty': result['result']['breach_penalty'],
                        'max_abs_inventory': result['max_abs_inventory'],
                        'sampled_max_drawdown': result['sampled_max_drawdown'],
                        'volume': result['result']['traded_volume'],
                        'final_inventory': result['result']['inventory'],
                    })
            for policy, _, _ in policies:
                selected = [r for r in records if r['regime'] == regime and r['policy'] == policy]
                print(regime, policy, 'mean_pnl', sum(r['pnl'] for r in selected) / len(selected),
                      'worst_pnl', min(r['pnl'] for r in selected),
                      'max_inventory', max(r['max_abs_inventory'] for r in selected), flush=True)
    output = Path('research/playground/defensive_stress.json')
    output.write_text(json.dumps({
        'warning': 'Invented stress cases, not recorded data or independent alpha validation. No tuning on these seeds.',
        'cycles': 30, 'seeds': args.seeds, 'records': records,
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
