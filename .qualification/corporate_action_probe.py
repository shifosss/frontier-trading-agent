"""Isolated native-engine dividend probe; no production module modifications."""
import json
from decimal import Decimal
from pathlib import Path
import pandas as pd
from nautilus_trader.backtest.config import BacktestEngineConfig, SimulationModuleConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.modules import SimulationModule
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide, PositionAdjustmentType
from nautilus_trader.model.events import PositionAdjusted
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.trading.strategy import Strategy

venue = Venue('PROBE')
instrument = Equity(InstrumentId(Symbol('TEST'), venue), Symbol('TEST'), USD, 2, Price.from_str('0.01'), Quantity.from_int(1), 0, 0)
times = [pd.Timestamp(s).value for s in ['2025-01-02T14:30Z', '2025-01-03T14:30Z', '2025-01-06T14:30Z']]

class DividendModule(SimulationModule):
    def __init__(self):
        super().__init__(SimulationModuleConfig())
        self.entitlement = None
        self.receivable = Decimal(0)
        self.paid = False
        self.trace = []
    def pre_process(self, data):
        if data.ts_event >= times[1] and self.entitlement is None:
            # Apply before the ex-date opening quote can fill orders.
            self.entitlement = sum(Decimal(str(p.quantity)) for p in self.cache.positions_open(instrument_id=instrument.id))
            self.receivable = self.entitlement * Decimal('1.00')
            self.trace.append({'event':'ex_date', 'quantity':str(self.entitlement), 'receivable':str(self.receivable)})
        if data.ts_event >= times[2] and not self.paid:
            self.exchange.adjust_account(Money(self.receivable, USD))
            self.trace.append({'event':'payment', 'cash_credit':str(self.receivable)})
            self.receivable = Decimal(0)
            self.paid = True
    def process(self, ts_now):
        pass
    def log_diagnostics(self, logger):
        pass
    def reset(self):
        pass

class ProbeStrategy(Strategy):
    def __init__(self, module, buy_on_ex=False):
        super().__init__()
        self.module = module
        self.buy_on_ex = buy_on_ex
        self.snapshots = []
    def on_start(self):
        self.subscribe_quote_ticks(instrument.id)
    def snapshot(self, when, price):
        cash = self.cache.account_for_venue(venue).balance_total(USD).as_decimal()
        shares = sum(Decimal(str(p.quantity)) for p in self.cache.positions_open(instrument_id=instrument.id))
        self.snapshots.append({'time':when, 'cash':str(cash), 'shares':str(shares), 'receivable':str(self.module.receivable), 'nav':str(cash + shares * price + self.module.receivable)})
    def on_quote_tick(self, tick):
        if tick.ts_event == times[0] and not self.buy_on_ex:
            self.submit_order(self.order_factory.market(instrument.id, OrderSide.BUY, Quantity.from_int(10)))
        if tick.ts_event == times[1]:
            side = OrderSide.BUY if self.buy_on_ex else OrderSide.SELL
            self.submit_order(self.order_factory.market(instrument.id, side, Quantity.from_int(5)))
        self.snapshot(str(tick.ts_event), tick.bid_price.as_decimal())
    def on_order_filled(self, event):
        self.snapshot('fill:' + str(event.ts_event), event.last_px.as_decimal())

def run(buy_on_ex=False):
    engine = BacktestEngine(BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True)))
    module = DividendModule()
    engine.add_venue(venue, OmsType.NETTING, AccountType.CASH, [Money(1000, USD)], modules=[module])
    engine.add_instrument(instrument)
    strategy = ProbeStrategy(module, buy_on_ex)
    engine.add_strategy(strategy)
    quotes = [QuoteTick(instrument.id, Price.from_str(price), Price.from_str(price), Quantity.from_int(100000), Quantity.from_int(100000), ts, ts) for ts, price in zip(times, ['100.00','99.00','99.00'])]
    engine.add_data(quotes)
    engine.run()
    result = {'trace':module.trace, 'snapshots':strategy.snapshots}
    cash = engine.cache.account_for_venue(venue).balance_total(USD).as_decimal()
    assert cash == (Decimal('505.00') if not buy_on_ex else Decimal('505.00'))
    assert module.entitlement == (0 if buy_on_ex else 10)
    if not buy_on_ex:
        assert any(Decimal(s['cash'])==495 and Decimal(s['receivable'])==10 and Decimal(s['nav'])==1000 for s in strategy.snapshots)
        assert Decimal(strategy.snapshots[-1]['nav']) == 1000
    # The only public PositionAdjusted quantity path does NOT adjust split cost basis.
    position = engine.cache.positions_open()[0]
    prior_basis = position.avg_px_open
    position.apply_adjustment(PositionAdjusted(position.trader_id, position.strategy_id, position.instrument_id, position.id, position.account_id, PositionAdjustmentType.FUNDING, Decimal(str(position.quantity)), None, 'probe only: unsupported split', UUID4(), times[-1]+1, times[-1]+1))
    result['unsupported_split'] = {'quantity':float(position.quantity), 'basis_before':prior_basis, 'basis_after':position.avg_px_open, 'unrealized_at_half_price':float(position.unrealized_pnl(Price.from_str('49.50')))}
    assert position.avg_px_open == prior_basis
    engine.dispose()
    return result

if __name__ == '__main__':
    result = {'pre_ex_holder':run(), 'ex_date_buyer':run(True)}
    Path('.qualification/corporate_action_probe.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
