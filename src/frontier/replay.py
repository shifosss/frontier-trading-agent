"""Actual Nautilus execution with an explicit synthetic opening-quote adapter."""

import hashlib
import json
import math
from collections import Counter
from decimal import Decimal
from pathlib import Path

import exchange_calendars as xcals
import nautilus_trader
import pandas as pd
from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.models import FeeModel
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.model.currencies import CAD, USD
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.trading.strategy import Strategy

from frontier.data import as_of, fx_as_of, load_dataset, session_endpoints
from frontier.domain import CALENDAR_BY_VENUE, MarketDataset, RunConfig
from frontier.metrics import calculate_metrics
from frontier.reports import write_report

VENUE = Venue("RESEARCH")
CURRENCIES = {"USD": USD, "CAD": CAD}


def code_identity():
    digest = hashlib.sha256()
    package = Path(__file__).parent
    names = (
        "domain.py",
        "data.py",
        "store.py",
        "fixtures.py",
        "replay.py",
        "metrics.py",
        "campaign.py",
        "reports.py",
    )
    paths = [package / name for name in names]
    lock = package.parent.parent / "uv.lock"
    if lock.exists():
        paths.append(lock)
    for path in sorted(paths):
        digest.update(path.name.encode())
        # Git may rewrite LF/CRLF on checkout; source identity is text, not line endings.
        digest.update(path.read_text(encoding="utf-8").encode("utf-8"))
    return "sha256:" + digest.hexdigest()


def save_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


class NativeFeeModel(FeeModel):
    """The engine debits each fill's native instrument currency."""

    def __init__(self, amount):
        self.amount = amount

    def get_commission(self, order, fill_qty, fill_px, instrument):
        return Money(self.amount if order.filled_qty == 0 else 0, instrument.quote_currency)


def opening_time(row, calendar, interval):
    session = str(row.event_time.tz_convert("America/Toronto").date())
    opening = calendar.session_open(session)
    if interval == "1d":
        return opening
    endpoints = session_endpoints(calendar, session, interval)
    index = endpoints.get_loc(row.event_time)
    return opening if index == 0 else endpoints[index - 1]


class ReplayStrategy(Strategy):
    def __init__(self, dataset, config, instruments, event_map):
        super().__init__()
        self.dataset = dataset
        self.run_config = config
        self.instruments_map = instruments
        self.original = {str(value.id): key for key, value in instruments.items()}
        self.specs = {i.id: i for i in dataset.manifest.instruments}
        self.event_map = event_map
        self.marks = {}
        self.pending = {}
        self.order_decisions = {}
        self.decisions = []
        self.fills = []
        self.curve = []
        self.seen_events = {key: set() for key in instruments}
        self.group_count = Counter(i.exposure_group for i in self.specs.values())
        self.drift = []

    def on_start(self):
        for instrument in self.instruments_map.values():
            self.subscribe_quote_ticks(instrument.id)

    def balances_now(self):
        account = self.cache.account_for_venue(VENUE)
        return {
            key: float(account.balance_total(currency).as_double())
            if account.balance_total(currency) is not None
            else 0.0
            for key, currency in CURRENCIES.items()
        }

    def positions_now(self):
        result = {}
        for position in self.cache.positions_open():
            result[self.original[str(position.instrument_id)]] = position
        return result

    def snapshot(self, timestamp):
        rate = fx_as_of(self.dataset.fx, timestamp)
        if rate is None:
            return None
        fx = float(rate.usd_cad)
        cash = self.balances_now()
        values = {"USD": 0.0, "CAD": 0.0}
        groups = Counter()
        for key, position in self.positions_now().items():
            value = float(position.quantity) * self.marks[key]
            currency = self.specs[key].currency
            values[currency] += value
            groups[self.specs[key].exposure_group] += value * (fx if currency == "USD" else 1)
        nav_cad = (cash["USD"] + values["USD"]) * fx + cash["CAD"] + values["CAD"]
        nav = nav_cad if self.run_config.base_currency == "CAD" else nav_cad / fx
        entry = {
            "timestamp": pd.Timestamp(timestamp).isoformat(),
            "nav": nav,
            "cash_usd": cash["USD"],
            "cash_cad": cash["CAD"],
            "positions_value_usd": values["USD"],
            "positions_value_cad": values["CAD"],
            "usd_cad": fx,
            "gross_exposure": (values["USD"] * fx + values["CAD"]) / nav_cad,
        }
        if self.curve and self.curve[-1]["timestamp"] == entry["timestamp"]:
            self.curve[-1] = entry
        else:
            self.curve.append(entry)
        for group, value in groups.items():
            if value / nav_cad > self.run_config.strategy.max_weight + 1e-9:
                self.drift.append(
                    {
                        "timestamp": entry["timestamp"],
                        "exposure_group": group,
                        "weight": value / nav_cad,
                    }
                )
        if min(cash.values()) < -0.000001:
            raise RuntimeError("Engine cash invariant violated")
        return entry

    def on_quote_tick(self, tick):
        for kind, row in self.event_map[(str(tick.instrument_id), tick.ts_event)]:
            self.process_observation(tick, kind, row)

    def process_observation(self, tick, kind, row):
        key = self.original[str(tick.instrument_id)]
        timestamp = pd.Timestamp(tick.ts_event, unit="ns", tz="UTC")
        if kind == "close":
            history = as_of(self.dataset.bars, timestamp)
            history = history.loc[history.instrument_id == key]
            latest = history.iloc[-1]
            self.marks[key] = float(latest.close)
            snapshot = self.snapshot(timestamp)
            # Revisions update knowable marks/features but never invent extra sessions.
            if row.event_time in self.seen_events[key]:
                return
            self.seen_events[key].add(row.event_time)
            count = len(self.seen_events[key])
            cfg = self.run_config.strategy
            warm = cfg.family in {"cash", "passive"} or len(history) >= cfg.lookback
            if snapshot is None or (count - 1) % cfg.rebalance_every:
                return
            signal = False
            reason = "warmup"
            if warm:
                closes = history.close.iloc[-cfg.lookback :]
                signal = (
                    cfg.family == "passive"
                    or cfg.family == "trend"
                    and closes.iloc[-1] > closes.mean()
                    or cfg.family == "reversion"
                    and closes.iloc[-1] < closes.iloc[0]
                )
                reason = {
                    "cash": "cash benchmark",
                    "passive": "equal capped allocation",
                    "trend": "close above trailing mean",
                    "reversion": "negative trailing close return",
                }[cfg.family]
            weight = min(cfg.max_weight, 1 / len(self.group_count))
            weight /= self.group_count[self.specs[key].exposure_group]
            decision = {
                "instrument_id": key,
                "decision_time": timestamp.isoformat(),
                "input_event_time": latest.event_time.isoformat(),
                "available_at": latest.available_at.isoformat(),
                "signal": int(signal),
                "target_weight": weight if signal else 0.0,
                "reason": reason,
                "execution_time": None,
                "status": "pending",
            }
            self.decisions.append(decision)
            if key in self.pending:
                self.pending[key]["status"] = "superseded"
            self.pending[key] = decision
            return
        snapshot = self.snapshot(timestamp)
        decision = self.pending.get(key)
        if not snapshot or not decision or pd.Timestamp(decision["decision_time"]) >= timestamp:
            return
        self.pending.pop(key)
        cash = self.balances_now()
        positions = self.positions_now()
        current = int(positions[key].quantity) if key in positions else 0
        currency = self.specs[key].currency
        fx = snapshot["usd_cad"]
        # Express budgeting in CAD; use actual opening ask only for execution sizing.
        nav_cad = snapshot["nav"] * (fx if self.run_config.base_currency == "USD" else 1)
        conversion = fx if currency == "USD" else 1
        fee = self.run_config.commission_per_order
        ask = float(tick.ask_price)
        bid = float(tick.bid_price)
        group = self.specs[key].exposure_group
        other = sum(
            float(p.quantity) * self.marks[k] * (fx if self.specs[k].currency == "USD" else 1)
            for k, p in positions.items()
            if k != key and self.specs[k].exposure_group == group
        )
        group_budget = max(
            0, self.run_config.strategy.max_weight * (nav_cad - fee * conversion) - other
        )
        target_budget = min(decision["target_weight"] * (nav_cad - fee * conversion), group_budget)
        target = max(0, math.floor(target_budget / conversion / max(ask, self.marks[key])))
        difference = target - current
        if difference > 0:
            difference = min(difference, max(0, math.floor((cash[currency] - fee) / ask)))
        if difference < 0 and cash[currency] + (-difference) * bid < fee:
            difference = 0
        decision["target_quantity"] = current + difference
        if not difference:
            decision["status"] = "no_order"
            return
        side = OrderSide.BUY if difference > 0 else OrderSide.SELL
        order = self.order_factory.market(
            tick.instrument_id, side, Quantity.from_int(abs(difference))
        )
        decision["status"] = "submitted"
        self.order_decisions[str(order.client_order_id)] = (decision, float(row.open))
        self.submit_order(order)

    def on_order_filled(self, event):
        decision, opening = self.order_decisions[str(event.client_order_id)]
        decision["execution_time"] = pd.Timestamp(event.ts_event, unit="ns", tz="UTC").isoformat()
        decision["status"] = "filled"
        key = self.original[str(event.instrument_id)]
        self.fills.append(
            {
                "instrument_id": key,
                "timestamp": decision["execution_time"],
                "side": event.order_side.name,
                "quantity": float(event.last_qty),
                "price": float(event.last_px),
                "commission": float(event.commission),
                "currency": self.specs[key].currency,
                "decision_time": decision["decision_time"],
                "synthetic_open": opening,
                "slippage_cost": abs(float(event.last_px) - opening) * float(event.last_qty),
            }
        )
        self.snapshot(pd.Timestamp(event.ts_event, unit="ns", tz="UTC"))

    def on_order_rejected(self, event):
        if str(event.client_order_id) in self.order_decisions:
            decision = self.order_decisions[str(event.client_order_id)][0]
            decision["status"] = "rejected"
            decision["rejection"] = event.reason


def replay_dataset(dataset: MarketDataset, config: RunConfig) -> dict:
    if dataset.manifest.dataset_id != config.dataset_id:
        raise ValueError("Run configuration dataset identity mismatch")
    if not dataset.actions.empty:
        raise ValueError("Known split/dividend actions are unsupported: replay rejected")
    incomplete = dataset.manifest.corporate_actions_status != "complete"
    if incomplete and not config.allow_incomplete_actions:
        raise ValueError("Action coverage incomplete: explicit allow_incomplete_actions required")
    if config.slippage_bps >= 10000:
        raise ValueError("slippage_bps must be below 10000 for positive synthetic bids")
    if fx_as_of(dataset.fx, dataset.bars.available_at.min()) is None:
        raise ValueError("No published FX before first price observation; supply prior dated FX")
    engine = BacktestEngine(BacktestEngineConfig(logging=LoggingConfig(bypass_logging=True)))
    try:
        engine.add_venue(
            VENUE,
            OmsType.NETTING,
            AccountType.CASH,
            [Money(config.initial_cash_usd, USD), Money(config.initial_cash_cad, CAD)],
            base_currency=None,
            fee_model=NativeFeeModel(config.commission_per_order),
        )
        instruments, events, event_map = {}, [], {}
        earliest = dataset.bars.sort_values("available_at").drop_duplicates(
            ["instrument_id", "event_time"], keep="first"
        )
        for index, spec in enumerate(dataset.manifest.instruments):
            instrument = Equity(
                InstrumentId(Symbol(f"I{index}"), VENUE),
                Symbol(spec.symbol),
                CURRENCIES[spec.currency],
                4,
                Price.from_str("0.0001"),
                Quantity.from_int(1),
                0,
                0,
            )
            instruments[spec.id] = instrument
            engine.add_instrument(instrument)
            calendar = xcals.get_calendar(
                CALENDAR_BY_VENUE[spec.venue],
                start=str(dataset.manifest.start.date() - pd.Timedelta(days=10)),
                end=str(dataset.manifest.end.date() + pd.Timedelta(days=10)),
            )
            rows = dataset.bars.loc[dataset.bars.instrument_id == spec.id]
            opening_rows = earliest.loc[earliest.instrument_id == spec.id]
            points = [
                ("open", row, opening_time(row, calendar, dataset.manifest.interval))
                for row in opening_rows.itertuples()
            ]
            points += [("close", row, row.available_at) for row in rows.itertuples()]
            for kind, row, timestamp in points:
                ns = timestamp.value
                event_key = (str(instrument.id), ns)
                if event_key in event_map:
                    event_map[event_key].append((kind, row))
                    continue
                event_map[event_key] = [(kind, row)]
                price = float(row.open if kind == "open" else row.close)
                spread = config.slippage_bps / 10000 if kind == "open" else 0
                bid = Price.from_str(f"{price * (1 - spread):.4f}")
                ask = Price.from_str(f"{price * (1 + spread):.4f}")
                events.append(
                    QuoteTick(
                        instrument.id,
                        bid,
                        ask,
                        Quantity.from_int(1_000_000_000),
                        Quantity.from_int(1_000_000_000),
                        ns,
                        ns,
                    )
                )
        strategy = ReplayStrategy(dataset, config, instruments, event_map)
        engine.add_strategy(strategy)
        engine.add_data(sorted(events, key=lambda event: (event.ts_init, str(event.instrument_id))))
        engine.run()
        positions = [
            {
                "instrument_id": key,
                "quantity": float(p.quantity),
                "average_basis": p.avg_px_open,
                "mark": strategy.marks[key],
                "currency": strategy.specs[key].currency,
            }
            for key, p in sorted(strategy.positions_now().items())
        ]
        limitations = list(dataset.manifest.limitations) + [
            (
                "Synthetic bid/ask inferred from OHLC opens; not observed quotes; "
                "fixed slippage, no volume impact"
            ),
            (
                "One consolidated RESEARCH cash venue; listing IDs and official "
                "exchange sessions preserved"
            ),
            (
                "Dated FX is reporting only; no FX conversion trades; most recent "
                "available close marks"
            ),
            "No terminal liquidation; final holdings and pending decisions remain open",
            "Descriptive in-sample engineering/research evidence; not out-of-sample validation",
            (
                "Historical bar opens reconstructed from earliest supplied "
                "vintage; not point-in-time certified"
            ),
        ]
        if incomplete:
            limitations.insert(
                0,
                (
                    "EXPLORATORY RAW-PRICE ONLY: incomplete corporate actions; no "
                    "total return or qualified equity execution"
                ),
            )
        summary = calculate_metrics(strategy.curve, strategy.fills, config, incomplete)
        # Attribute every engine fill, including earlier closed/reopened netting lifecycles.
        # Engine notional Money preserves native cash rounding; Position P&L does not.
        contribution = {}
        for fill in strategy.fills:
            key = fill["instrument_id"]
            spec = strategy.specs[key]
            notional = (
                instruments[key]
                .notional_value(
                    Quantity.from_int(int(fill["quantity"])),
                    Price.from_str(f"{fill['price']:.4f}"),
                )
                .as_decimal()
            )
            signed = notional if fill["side"] == "SELL" else -notional
            bucket = contribution.setdefault(spec.venue, {"USD": Decimal(0), "CAD": Decimal(0)})
            bucket[spec.currency] += signed - Decimal(str(fill["commission"]))
        for position in positions:
            spec = strategy.specs[position["instrument_id"]]
            bucket = contribution.setdefault(spec.venue, {"USD": Decimal(0), "CAD": Decimal(0)})
            bucket[spec.currency] += Decimal(str(position["quantity"])) * Decimal(
                str(position["mark"])
            )
        summary["per_market_contribution"] = {
            venue: {currency: float(amount) for currency, amount in values.items()}
            for venue, values in contribution.items()
        }
        summary.update(
            mode=dataset.manifest.mode,
            evidence_label="exploratory_raw_price"
            if incomplete
            else "synthetic_engineering"
            if dataset.manifest.mode == "synthetic_fixture"
            else "limited_raw_price_replay",
            start=strategy.curve[0]["timestamp"],
            end=strategy.curve[-1]["timestamp"],
            base_currency=config.base_currency,
            limitations=limitations,
        )
        return {
            "schema_version": 1,
            "config": config.model_dump(mode="json"),
            "dataset": dataset.manifest.model_dump(mode="json"),
            "summary": summary,
            "equity_curve": strategy.curve,
            "decisions": strategy.decisions,
            "fills": strategy.fills,
            "positions": positions,
            "balances": strategy.balances_now(),
            "exposure_drift": strategy.drift,
            "unfilled_intents": [
                d for d in strategy.decisions if d["status"] in {"pending", "submitted", "rejected"}
            ],
            "engine_identity": {
                "name": "nautilus_trader",
                "version": nautilus_trader.__version__,
                "venue_count": 1,
                "account_count": len(engine.cache.accounts()),
                "simulated_venue": str(VENUE),
                "quotes": "synthetic_from_raw_bars",
            },
        }
    finally:
        engine.dispose()


def run_research(config: RunConfig, data_root: Path, registry, artifact_root: Path) -> dict:
    mode = "historical"
    try:
        manifest = json.loads((Path(data_root) / config.dataset_id / "manifest.json").read_text())
        candidate_mode = manifest.get("mode")
        if candidate_mode in {"historical", "synthetic_fixture"}:
            mode = candidate_mode
    except (OSError, ValueError):
        pass
    run_id = registry.start_run(config, mode, code_identity())
    directory = Path(artifact_root) / run_id
    try:
        dataset = load_dataset(data_root, config.dataset_id)
        access = registry.record_evaluation_access(
            config.dataset_id,
            dataset.manifest.start.isoformat(),
            dataset.manifest.end.isoformat(),
            run_id,
            "run_research",
        )
        result = replay_dataset(dataset, config)
        result["evaluation_access"] = {
            "start": dataset.manifest.start.isoformat(),
            "end": dataset.manifest.end.isoformat(),
            "prior_overlaps": access,
            "scope": "same immutable dataset identity; no cross-vintage secrecy claim",
        }
        save_json(directory / "result.json", result)
        write_report(result, directory / "report.html")
        registry.finish_run(run_id, result["summary"], str(directory.resolve()))
    except Exception as exc:
        registry.fail_run(run_id, f"{type(exc).__name__}: {exc}")
        raise
    return registry.get_run(run_id)
