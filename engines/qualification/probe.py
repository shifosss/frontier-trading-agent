"""Synthetic engineering fixtures only; no broker, capital, or data service access."""
from __future__ import annotations
import json
import platform
from decimal import Decimal
from pathlib import Path
import nautilus_trader
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.config import BacktestEngineConfig, SimulationModuleConfig
from nautilus_trader.backtest.models import FixedFeeModel
from nautilus_trader.backtest.modules import SimulationModule
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model.currencies import USD, CAD
from nautilus_trader.model.data import QuoteTick, Bar, BarType
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide, PositionAdjustmentType
from nautilus_trader.model.events import PositionAdjusted
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.trading.strategy import Strategy

T0 = 1_735_833_600_000_000_000
SPECS = [('SYNTH_US', 'XNAS', USD), ('SYNTH_CA', 'XTSE', CAD)]

class ExchangeAccess(SimulationModule):
    def __init__(self):
        super().__init__(SimulationModuleConfig())
    def process(self, ts_now): pass
    def log_diagnostics(self, logger): pass
    def reset(self): pass

class ProbeStrategy(Strategy):
    def __init__(self, instruments, modules, mode):
        super().__init__()
        self.instruments = instruments
        self.modules = modules
        self.mode = mode
        self.seen = {}
        self.resting = {}
        self.fills = []
        self.action_checks = {}
        self.bars = 0
    def on_start(self):
        for instrument in self.instruments:
            self.subscribe_quote_ticks(instrument.id)
            self.subscribe_bars(BarType.from_str(f'{instrument.id}-1-MINUTE-LAST-EXTERNAL'))
    def on_bar(self, bar): self.bars += 1
    def on_order_filled(self, event):
        self.fills.append({'instrument': str(event.instrument_id), 'side': event.order_side.name,
                           'quantity': str(event.last_qty), 'price': str(event.last_px),
                           'commission': str(event.commission)})
    def on_quote_tick(self, tick):
        iid = tick.instrument_id
        n = self.seen.get(iid, 0) + 1
        self.seen[iid] = n
        instrument = self.cache.instrument(iid)
        currency = instrument.quote_currency
        if n == 1:
            self.submit_order(self.order_factory.market(iid, OrderSide.BUY, Quantity.from_int(10)))
        if n == 2:
            order = self.order_factory.limit(iid, OrderSide.SELL, Quantity.from_int(5), Price.from_str('300.00'))
            self.resting[iid] = order
            self.submit_order(order)
        if n == 3 and self.mode != 'baseline':
            position = self.cache.positions_open(instrument_id=iid)[0]
            exchange = self.modules[iid.venue].exchange
            before = position.to_dict()
            exchange.adjust_account(Money(5, currency))
            position.apply_adjustment(PositionAdjusted(
                position.trader_id, position.strategy_id, iid, position.id, position.account_id,
                PositionAdjustmentType.FUNDING, None, Money(5, currency), 'SYNTHETIC dividend: 10 x 0.50',
                UUID4(), tick.ts_event, tick.ts_init))
            self.action_checks[str(iid)] = {'dividend_before': before['realized_pnl'],
                'dividend_after': str(position.realized_pnl), 'dividend_quantity': str(position.quantity)}
            if self.mode == 'split':
                position.apply_adjustment(PositionAdjusted(
                    position.trader_id, position.strategy_id, iid, position.id, position.account_id,
                    PositionAdjustmentType.FUNDING, Decimal('10'), None, 'SYNTHETIC 2-for-1 split experiment',
                    UUID4(), tick.ts_event, tick.ts_init))
                self.modify_order(self.resting[iid], quantity=Quantity.from_int(10), price=Price.from_str('150.00'))
                self.action_checks[str(iid)]['split_average_basis'] = position.avg_px_open

def run(mode):
    engine = BacktestEngine(BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True)))
    instruments, modules, events = [], {}, []
    for symbol, venue_name, currency in SPECS:
        venue = Venue(venue_name)
        module = ExchangeAccess()
        modules[venue] = module
        engine.add_venue(venue, OmsType.NETTING, AccountType.CASH,
            [Money(10000, USD), Money(10000, CAD)], base_currency=None,
            fee_model=FixedFeeModel(Money(1, currency)), modules=[module])
        instrument = Equity(InstrumentId(Symbol(symbol), venue), Symbol(symbol), currency,
            2, Price.from_str('0.01'), Quantity.from_int(1), 0, 0)
        instruments.append(instrument)
        engine.add_instrument(instrument)
        for index in range(4):
            price = '50.00' if mode == 'split' and index == 3 else '100.00'
            ts = T0 + index * 60_000_000_000
            events.append(QuoteTick(instrument.id, Price.from_str(price), Price.from_str(price),
                Quantity.from_int(1000), Quantity.from_int(1000), ts, ts))
        ts = T0 + 240_000_000_000
        price = Price.from_str('50.00' if mode == 'split' else '100.00')
        events.append(Bar(BarType.from_str(f'{instrument.id}-1-MINUTE-LAST-EXTERNAL'),
            price, price, price, price, Quantity.from_int(1000), ts, ts))
    strategy = ProbeStrategy(instruments, modules, mode)
    engine.add_strategy(strategy)
    events.sort(key=lambda event: event.ts_init)
    engine.add_data(events)
    engine.run()
    positions = []
    for position in sorted(engine.cache.positions(), key=lambda p: str(p.instrument_id)):
        positions.append({'instrument': str(position.instrument_id), 'quantity': str(position.quantity),
            'average_basis': position.avg_px_open, 'realized_pnl': str(position.realized_pnl),
            'unrealized_pnl': str(position.unrealized_pnl(Price.from_str('50.00' if mode == 'split' else '100.00'))),
            'adjustment_count': len(position.adjustments)})
    balances = {str(venue): {str(currency): str(balance.total) for currency, balance in
        engine.cache.account_for_venue(venue).balances().items()} for venue in modules}
    resting = [{'instrument': str(iid), 'quantity': str(order.quantity), 'price': str(order.price),
                'status': order.status.name} for iid, order in strategy.resting.items()]
    result = {'mode': mode, 'input_quote_count': 8, 'input_bar_count': 2, 'bars_received': strategy.bars,
              'fills': strategy.fills, 'balances': balances, 'positions': positions,
              'fx_without_quote': {str(v): engine.cache.get_xrate(v, CAD, USD) for v in modules}, 'resting_orders': resting, 'actions': strategy.action_checks}
    engine.dispose()
    return result

def main():
    first = [run(mode) for mode in ('baseline', 'dividend', 'split')]
    second = [run(mode) for mode in ('baseline', 'dividend', 'split')]
    assert first == second, 'Normalized financial/order content differs on repeat'
    for result in first:
        assert len(result['fills']) == 2 and result['bars_received'] == 2
        for _, venue, currency in SPECS:
            expected_cash = '8999.00' if result['mode'] == 'baseline' else '9004.00'
            assert result['balances'][venue][str(currency)] == f'{expected_cash} {currency}'
            other_currency = CAD if currency == USD else USD
            assert result['balances'][venue][str(other_currency)] == f'10000.00 {other_currency}'
        for position in result['positions']:
            assert position['quantity'] == ('20' if result['mode'] == 'split' else '10')
            assert position['average_basis'] == 100.0
            assert position['realized_pnl'].split()[0] == ('-1.00' if result['mode'] == 'baseline' else '4.00')
            assert position['unrealized_pnl'].split()[0] == ('-1000.00' if result['mode'] == 'split' else '0.00')
        for order in result['resting_orders']:
            assert order['quantity'] == ('10' if result['mode'] == 'split' else '5')
            assert order['price'] == ('150.00' if result['mode'] == 'split' else '300.00')
            assert order['status'] == 'ACCEPTED', order
    report = {'fixture': 'SYNTHETIC ENGINEERING ONLY; no market data or brokerage',
        'engine': nautilus_trader.__version__, 'python': platform.python_version(),
        'repeat_equal': True,
        'normalization': 'Exclude generated event/order/position UUIDs and wall-clock runtime; preserve instrument, side, quantity, price, commission, order status, cash, basis and P&L.',
        'results': first}
    path = Path(__file__).parent / 'evidence' / 'nautilus-probe.json'
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))

if __name__ == '__main__': main()

