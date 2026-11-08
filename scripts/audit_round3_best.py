"""Audit actual fills and decision state of the highest-scoring round 3 run."""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from simulator.models import Side, OrderStatus
from simulator.simulator import ExchangeSimulator, SimulationConfig
from strategies.adaptive_ml_regime import AdaptiveMakerMLStrategy

OUT = ROOT / 'logs/round3_best_audit'


class AuditMaker(AdaptiveMakerMLStrategy):
    def __init__(self):
        super().__init__(crash_drop=1e9, recovery_rise=None)
        self.fill_rows = []
        self.quote_rows = []
        self.state_rows = []
        self.last_quote = None
        self.last_second = -1
        self.forecast_value = 0.0

    def on_order_book_change(self, snapshot, trades):
        super().on_order_book_change(snapshot, trades)
        if self._best != self.last_quote:
            self.quote_rows.append((snapshot.timestamp_us / 1e6, *self._best))
            self.last_quote = self._best
        sec = snapshot.timestamp_us // 1000000
        if sec != self.last_second:
            self.forecast_value = self._forecast() if self._hist else 0.0
            self.state_rows.append((snapshot.timestamp_us / 1e6, self._inventory, self._eff_limit,
                                    self._center, self.forecast_value))
            self.last_second = sec

    def on_private_order_update(self, event):
        record = self._orders.get(event.order_id)
        rescue = event.order_id in self._iocs
        before = self._inventory
        pending_cancel = bool(record and record[3])
        side = record[0] if record else (Side.BUY if self._iocs.get(event.order_id, 0) > 0 else Side.SELL)
        super().on_private_order_update(event)
        if event.filled_quantity and event.status in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED):
            bid, ask = self._best or (np.nan, np.nan)
            self.fill_rows.append((event.timestamp_us / 1e6, event.order_id, 1 if side == Side.BUY else -1,
                event.filled_quantity, event.fill_price, before, self._inventory, self._eff_limit, self._center,
                self.forecast_value, bid, ask, pending_cancel, rescue))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    strategy = AuditMaker()
    engine = ExchangeSimulator(strategy, SimulationConfig(order_accept_delay_ms=5,
        max_position=100, max_potential_position=1000, position_breach_penalty_per_second=10000))
    result = engine.run(ROOT / 'data/round3_public.csv')
    expected = json.loads((ROOT / 'logs/round3_analysis/ablations/no_crash_bias/result.json').read_text())
    assert result.model_dump() == expected, 'Instrumentation changed the result'
    (OUT / 'result.json').write_text(json.dumps(result.model_dump(), indent=2))
    fills = pd.DataFrame(strategy.fill_rows, columns=['time','order_id','sign','quantity','price','inventory_before',
        'inventory_after','limit','center','forecast','bid','ask','pending_cancel','rescue'])
    quotes = pd.DataFrame(strategy.quote_rows, columns=['time','bid','ask'])
    quotes['mid'] = (quotes.bid + quotes.ask) / 2
    state = pd.DataFrame(strategy.state_rows, columns=['time','inventory','limit','center','forecast'])
    state.to_csv(OUT / 'decisions.csv', index=False)
    quotes.to_csv(OUT / 'quotes.csv', index=False)
    assert fills.quantity.sum() == result.traded_volume
    assert (fills.sign * fills.quantity).sum() == result.inventory
    assert -(fills.sign * fills.quantity * fills.price).sum() == result.cash
    end = engine._last_event_us / 1e6
    for h in [0.005, 0.1, 1, 5, 10]:
        targets = fills.time.to_numpy() + h
        indices = np.searchsorted(quotes.time, targets, side='right') - 1
        future = quotes.mid.to_numpy()[np.maximum(0, indices)]
        values = fills.sign.to_numpy() * (future - fills.price.to_numpy())
        fills[f'edge_{h}s'] = np.where((indices >= 0) & (targets <= end), values, np.nan)
    fills['risk_band'] = pd.cut(fills.forecast, [-np.inf,1.4,1.8,2.2,3,np.inf]).astype(str)
    fills['growing'] = fills.inventory_after.abs() > fills.inventory_before.abs()
    fills.to_csv(OUT / 'fills.csv', index=False)
    rows = []
    for field in ['risk_band','pending_cancel','rescue','growing','center']:
        for key, group in fills.groupby(field):
            row = {'field':field,'group':str(key),'fills':len(group),'lots':int(group.quantity.sum())}
            for h in [0.005,0.1,1,5,10]:
                valid = group[f'edge_{h}s'].notna()
                row[f'edge_{h}s'] = np.average(group.loc[valid,f'edge_{h}s'], weights=group.loc[valid,'quantity']) if valid.any() else np.nan
            rows.append(row)
    grouped = pd.DataFrame(rows)
    grouped.to_csv(OUT / 'fill_groups.csv', index=False)
    pnl = pd.DataFrame(engine.pnl_curve(result.pnl), columns=['time_us','pnl'])
    pnl['time'] = pnl.time_us / 1e6
    pnl['change'] = pnl.pnl.diff().fillna(pnl.pnl)
    pnl['drawdown'] = pnl.pnl - pnl.pnl.cummax()
    pnl.to_csv(OUT / 'pnl.csv', index=False)
    minute = pnl.groupby((pnl.time // 60).astype(int)).agg(pnl=('change','sum'))
    minute.to_csv(OUT / 'minute_pnl.csv')
    worst = pnl.nsmallest(15,'change')[['time','change','pnl','drawdown']]
    worst.to_csv(OUT / 'worst_seconds.csv', index=False)
    print('Reproduced:', result.model_dump())
    print('WORST SECONDS\n',worst.to_string(index=False))
    print('FILL GROUPS\n',grouped.to_string(index=False))
    print('WORST MINUTES\n',minute.nsmallest(8,'pnl').to_string())
    print('CONTROL SUMMARY',state.groupby('center').agg(seconds=('time','size'),mean_abs_inventory=('inventory',lambda x:x.abs().mean())).to_dict())
    print('BREACH FILLS\n', fills[fills.inventory_after.abs()>100].to_string(index=False))


if __name__ == '__main__':
    main()
