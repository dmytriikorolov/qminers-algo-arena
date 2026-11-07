"""Chronological v2 checks with explicit split labels; no parameter search."""

import argparse
import json
from pathlib import Path

from scripts.playground_experiments import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('validation', 'final'), required=True)
    args = parser.parse_args()
    data = Path('data/sample_v2.csv')
    if args.stage == 'validation':
        prefix = Path('logs/v2/validation.csv')
        prefix.parent.mkdir(parents=True, exist_ok=True)
        with data.open() as source, prefix.open('w') as target:
            target.write(next(source))
            for line in source:
                if float(line.split(',', 1)[0]) > 3800:
                    break
                target.write(line)
        data = prefix
    cutoff = 1800 if args.stage == 'validation' else 3800
    cases = [('maker', 'strategies/v2_inventory_maker.py', {}),
             ('flow2', 'strategies/playground_flow.py', {'LOT': 2, 'LIMIT': 2}),
             ('defensive', 'strategies/defensive_flow.py', {}),
             ('noop', 'strategies/template_strategy.py', {})]
    for name, strategy, parameters in cases:
        output = Path('research/v2') / f'{name}_{args.stage}.json'
        record = run(Path(strategy), data, parameters, output, cutoff)
        record['split_elapsed_s'] = cutoff
        record['pnl_at_split'] = record.pop('development_pnl')
        record['pnl_after_split'] = record.pop('final_20m_pnl')
        record['first_three_20m_pnl'] = record.pop('chronological_20m_pnl')
        output.write_text(json.dumps(record, indent=2) + '\n')
        print(name, args.stage, 'pnl', record['result']['pnl'],
              'after_split', record['pnl_after_split'],
              'drawdown', record['sampled_max_drawdown'], flush=True)


if __name__ == '__main__':
    main()
