"""Scheduled paper operation: frozen decisions, durable intents, broker-owned fills.

The broker owns the accounting. This journal verifies cash and share changes from
its order observations; it never turns a research bar into a fabricated fill.
"""

import hashlib
import math
from datetime import datetime, timezone
from pathlib import Path

import exchange_calendars as xcals
import pandas as pd

from frontier.operator_store import OperatorStore, encode, operator_lock
from frontier.paper_broker import AlpacaPaper, SubmissionUncertain
from frontier.paper_risk import settlement_balance, update_risk
from frontier.scan_data import capture_universe, load_universe, read_capture
from frontier.sources import boc_rows, fetch_boc_fx
from frontier.swing_policy import SwingPolicy, plan_portfolio

TERMINAL = {"filled", "canceled", "expired", "rejected", "replaced"}
REQUIREMENTS = [
    "Dedicated Alpaca paper account and locally configured paper API keys.",
    "Paper cash must match the declared starting USD balance; no margin buying power.",
    "US stocks first. Canadian API execution, options and live deployment remain unfinished.",
    "Paper observations do not establish strategy profitability or live execution quality.",
    "Paper simulation omits dividends and real market impact; results are not live returns.",
]


def _now():
    return datetime.now(timezone.utc).isoformat()


def operator_identity():
    digest = hashlib.sha256()
    for name in (
        "operator.py",
        "operator_store.py",
        "paper_risk.py",
        "paper_broker.py",
        "swing_policy.py",
        "scan_data.py",
        "sources.py",
    ):
        digest.update((Path(__file__).parent / name).read_text("utf-8").encode())
    return digest.hexdigest()


def fx_reference(workspace, as_of):
    timestamp = pd.Timestamp(as_of)
    capture = fetch_boc_fx(
        str((timestamp - pd.Timedelta(days=14)).date()),
        str(timestamp.date()),
        Path(workspace) / "artifacts/sources/cache",
        refresh=True,
    )
    rows = boc_rows(capture["payload"], capture["retrieved_at"])
    available = rows.loc[pd.to_datetime(rows.available_at, utc=True) <= timestamp]
    if available.empty:
        raise ValueError("No published CAD valuation reference")
    row = available.sort_values("available_at").iloc[-1]
    if timestamp - pd.Timestamp(row.available_at) > pd.Timedelta(days=7):
        raise ValueError("CAD valuation reference is stale")
    rate = float(row.usd_cad)
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError("Invalid CAD valuation reference")
    return {
        "usd_cad": rate,
        "available_at": row.available_at,
        "source": row.source,
        "raw_path": capture["raw_path"],
        "sha256": hashlib.sha256(Path(capture["raw_path"]).read_bytes()).hexdigest(),
    }


def operator_status(workspace):
    store = OperatorStore(workspace)
    config = store.get("config")
    status = store.get(
        "status",
        {
            "status": "setup_required",
            "message": "Paper operator built; no paper account connected.",
        },
    )
    return {
        "mode": "paper",
        "initialized": config is not None,
        **status,
        "account": (
            {
                "account_id": config["account_id"],
                "initial_cash_usd": config["initial_cash_usd"],
                "last_snapshot": store.get("snapshot"),
                "risk": store.get("risk"),
            }
            if config
            else None
        ),
        "policy": config["policy"] if config else SwingPolicy().model_dump(mode="json"),
        "latest_cycle": store.latest_cycle(),
        "orders": store.orders(),
        "requirements": REQUIREMENTS,
    }


def _validate_snapshot(snapshot, account_id, as_of):
    account = snapshot["account"]
    if account["id"] != account_id or account.get("currency") != "USD":
        raise ValueError("Broker identity or currency differs from the frozen paper mandate")
    if account.get("status") != "ACTIVE" or account.get("trading_blocked"):
        raise ValueError("Paper account is not available for trading")
    stamp = pd.Timestamp(snapshot["clock"]["timestamp"])
    if stamp.tzinfo is None or abs(stamp - pd.Timestamp(as_of)) > pd.Timedelta(minutes=2):
        raise ValueError("Paper broker clock is stale or lacks a timezone")
    cash, equity = float(account["cash"]), float(account["equity"])
    if not all(math.isfinite(v) and v >= 0 for v in (cash, equity)):
        raise ValueError("Cash-only mandate requires finite nonnegative broker cash and equity")
    for position in snapshot["positions"]:
        qty = float(position["qty"])
        if not math.isfinite(qty) or qty <= 0 or not qty.is_integer():
            raise ValueError("This paper mandate supports long whole-share positions only")
        if position.get("asset_class", "us_equity") != "us_equity":
            raise ValueError("Unsupported position in the dedicated US paper account")
        mark = float(position["market_value"])
        if not math.isfinite(mark) or mark < 0:
            raise ValueError("Broker position mark must be finite and nonnegative")
    # REST account and positions are observed separately, so their marks are not atomic.
    long_value = float(account.get("long_market_value", equity - cash))
    short_value = float(account.get("short_market_value", 0))
    if not math.isfinite(long_value) or long_value < 0 or short_value != 0:
        raise ValueError("Paper account contains invalid or short market exposure")
    if abs(cash + long_value - equity) > 0.02:
        raise ValueError("Broker account cash and long market value do not reconcile to equity")


def initialize_paper(workspace, account_id, cash_usd, *, broker=None, as_of=None, fx=None):
    if not math.isfinite(cash_usd) or cash_usd <= 0:
        raise ValueError("Starting simulated USD cash must be positive")
    owned = broker is None
    broker = broker or AlpacaPaper()
    try:
        with operator_lock(workspace):
            store = OperatorStore(workspace)
            if store.get("config"):
                raise ValueError("Paper mandate already initialized; existing state is preserved")
            timestamp = as_of or _now()
            snapshot = broker.snapshot()
            _validate_snapshot(snapshot, account_id, timestamp)
            if snapshot["positions"] or snapshot["orders"]:
                raise ValueError("Initialize with an empty dedicated paper account")
            if abs(float(snapshot["account"]["cash"]) - cash_usd) > 0.005:
                raise ValueError(
                    "Paper account cash must match the declared simulated starting cash"
                )
            reference = fx or fx_reference(workspace, timestamp)
            policy = SwingPolicy()
            config = {
                "account_id": account_id,
                "initial_cash_usd": cash_usd,
                "policy": policy.model_dump(mode="json"),
                "code_identity": operator_identity(),
                "universe": load_universe(workspace),
                "initialized_at": timestamp,
            }
            risk = update_risk(None, cash_usd * reference["usd_cad"])
            snapshot["fx"] = reference
            # The mandate and initial valuation must either both exist or neither exist.
            with store.connect() as connection:
                for key, value in (
                    ("config", config),
                    ("risk", risk),
                    ("snapshot", snapshot),
                    ("position_state", {}),
                    ("paused", False),
                ):
                    connection.execute("INSERT INTO state VALUES (?,?)", (key, encode(value)))
            store.set(
                "status",
                {
                    "status": "ready",
                    "message": "Paper account initialized. Run a cycle to reconcile and plan.",
                },
            )
            return operator_status(workspace)
    finally:
        if owned:
            broker.close()


def _check_order(record, observed):
    payload = record["payload"]
    if (
        observed.get("client_order_id") != record["id"]
        or any(
            observed.get(key) != payload[key] for key in ("symbol", "side", "type", "time_in_force")
        )
        or float(observed["qty"]) != float(payload["qty"])
    ):
        raise ValueError("Broker order differs from the saved intent")
    if payload["type"] == "limit" and float(observed["limit_price"]) != float(
        payload["limit_price"]
    ):
        raise ValueError("Broker limit differs from the saved intent")
    filled = float(observed.get("filled_qty", 0))
    previous = record.get("broker") or {}
    if filled > 0:
        observed["_first_fill_at"] = (
            previous.get("_first_fill_at")
            or observed.get("filled_at")
            or observed.get("updated_at")
        )
    if not math.isfinite(filled) or not float(previous.get("filled_qty", 0)) <= filled <= float(
        payload["qty"]
    ):
        raise ValueError("Broker cumulative fill decreased or exceeds the saved quantity")


def _reconcile(store, broker):
    uncertain = []
    for record in store.orders():
        if record["state"] not in {"SUBMITTING", "UNKNOWN", "BROKER"}:
            continue
        # ponytail: retain terminal fill evidence; account mismatches expose later corrections.
        if record["state"] == "BROKER" and record["broker"]["status"] in TERMINAL:
            continue
        observed = broker.get_order(record["id"])
        if observed is None:
            store.update_order(
                record["id"],
                "UNKNOWN",
                record["broker"],
                "Submission outcome unresolved; automatic resubmission prohibited",
            )
            uncertain.append(record["id"])
        else:
            _check_order(record, observed)
            store.update_order(record["id"], "BROKER", observed)
    rejected_exits = [
        r
        for r in store.orders()
        if r["payload"]["side"] == "sell"
        and (r["state"] == "REJECTED" or (r["broker"] and r["broker"].get("status") == "rejected"))
    ]
    if rejected_exits:
        raise ValueError("Paper exit rejected; explicit recovery is required")
    if uncertain:
        raise ValueError("Unresolved paper submission; lookup has not established the outcome")


def _balances(store, snapshot, as_of, *, declared_flow=0.0):
    config = store.get("config")
    orders = store.orders()
    balance = settlement_balance(config["initial_cash_usd"], store.flows(), orders, as_of)
    if abs(balance["expected_cash"] + declared_flow - float(snapshot["account"]["cash"])) > 0.02:
        raise ValueError(
            "Unexplained paper cash change; reconcile or explicitly record its funding flow"
        )
    actual = {p["symbol"]: float(p["qty"]) for p in snapshot["positions"]}
    if actual != balance["positions"]:
        raise ValueError(
            "Paper holdings differ from recorded fills; corporate/manual change unresolved"
        )
    known = {r["id"] for r in orders}
    if any(o.get("client_order_id") not in known for o in snapshot["orders"]):
        raise ValueError("Unmanaged order in the dedicated paper account")
    balance["spendable"] = min(balance["spendable"], float(snapshot["account"]["cash"]))
    return balance


def _position_state(store, positions):
    saved = store.get("position_state", {})
    quantities, entries = {}, {}
    for record in store.orders():
        broker = record.get("broker")
        if not broker or not float(broker.get("filled_qty", 0)):
            continue
        symbol = record["payload"]["symbol"]
        quantity = float(broker["filled_qty"])
        if record["payload"]["side"] == "buy":
            if quantities.get(symbol, 0) == 0:
                stamp = (
                    broker.get("_first_fill_at") or broker.get("filled_at") or broker["updated_at"]
                )
                entries[symbol] = str(pd.Timestamp(stamp).tz_convert("America/New_York").date())
            quantities[symbol] = quantities.get(symbol, 0) + quantity
        else:
            quantities[symbol] = quantities.get(symbol, 0) - quantity
    result = {}
    for position in positions:
        symbol = position["symbol"]
        if symbol not in entries:
            continue
        state = {"entry_session": entries[symbol]}
        if saved.get(symbol, {}).get("entry_session") == entries[symbol]:
            if "peak_close" in saved[symbol]:
                state["peak_close"] = saved[symbol]["peak_close"]
        result[symbol] = state
    return result


def _save_plan(store, session, plan, capture):
    config = store.get("config")
    intents = []
    for index, intent in enumerate(plan["intents"]):
        identity = (
            "ft-"
            + hashlib.sha256(
                encode(
                    [config["account_id"], session, config["code_identity"], index, intent]
                ).encode()
            ).hexdigest()[:40]
        )
        payload = {
            k: v
            for k, v in intent.items()
            if k in {"symbol", "side", "qty", "type", "time_in_force", "limit_price"}
        }
        payload["client_order_id"] = identity
        intents.append({"id": identity, "payload": payload})
    store.save_plan(session, plan["decision_at"], plan, capture, intents)


def _submit_due(store, broker, snapshot, as_of, halted):
    now = pd.Timestamp(as_of or _now())
    submitted = False
    for record in store.orders():
        if record["state"] != "PLANNED":
            continue
        payload = record["payload"]
        now = pd.Timestamp(as_of or _now())
        if now >= pd.Timestamp(record["expires_at"]) or (halted and payload["side"] == "buy"):
            store.update_order(record["id"], "SKIPPED", error="Expired or halted before submission")
            continue
        if not snapshot["clock"]["is_open"] or now < pd.Timestamp(record["eligible_at"]):
            continue
        if payload["side"] == "buy":
            budget = settlement_balance(
                store.get("config")["initial_cash_usd"],
                store.flows(),
                store.orders(),
                as_of or _now(),
            )["spendable"]
            budget = min(budget, float(snapshot["account"]["cash"]))
            if float(payload["qty"]) * float(payload["limit_price"]) > budget + 1e-9:
                store.update_order(record["id"], "SKIPPED", error="Insufficient settled paper cash")
                continue
            policy = store.get("config")["policy"]
            equity = float(snapshot["account"]["equity"])
            cost = float(payload["qty"]) * float(payload["limit_price"])
            gross = max(
                sum(float(p["market_value"]) for p in snapshot["positions"]),
                float(snapshot["account"].get("long_market_value", 0)),
            )
            reserved = sum(
                (float(r["payload"]["qty"]) - float(r["broker"].get("filled_qty", 0)))
                * float(r["payload"]["limit_price"])
                for r in store.orders()
                if r["state"] == "BROKER"
                and r["payload"]["side"] == "buy"
                and r["broker"]["status"] not in TERMINAL
            )
            if cost > equity * policy["max_position_fraction"] or (
                gross + reserved + cost > equity * policy["max_gross_fraction"]
            ):
                store.update_order(
                    record["id"], "SKIPPED", error="Current paper exposure cap exceeded"
                )
                continue
            asset = broker.asset(payload["symbol"])
            if not asset.get("tradable") or asset.get("status") != "active":
                store.update_order(record["id"], "SKIPPED", error="Broker asset is not tradable")
                continue
        else:
            quantities = {p["symbol"]: float(p["qty"]) for p in snapshot["positions"]}
            if quantities.get(payload["symbol"], 0) < float(payload["qty"]):
                store.update_order(record["id"], "SKIPPED", error="Sell quantity exceeds holdings")
                continue
        store.update_order(record["id"], "SUBMITTING")
        submitted = True
        try:
            observed = broker.submit(payload)
        except SubmissionUncertain:
            store.update_order(record["id"], "UNKNOWN", error="Paper submission outcome uncertain")
            raise ValueError(
                "Paper submission uncertain; reconcile by client order ID before continuing"
            )
        except RuntimeError:
            store.update_order(
                record["id"], "REJECTED", error="Paper broker explicitly rejected request"
            )
            if payload["side"] == "sell":
                raise ValueError("Paper exit rejected; review the saved order before continuing")
            continue
        # A malformed acknowledgment also stays recoverable via its durable SUBMITTING record.
        _check_order(record, observed)
        store.update_order(record["id"], "BROKER", observed)
        # Each accepted order can change gross exposure before the next submission.
        reference = snapshot["fx"]
        _reconcile(store, broker)
        snapshot = broker.snapshot()
        observation_time = as_of or _now()
        _validate_snapshot(snapshot, store.get("config")["account_id"], observation_time)
        _balances(store, snapshot, observation_time)
        snapshot["fx"] = reference
        risk = update_risk(
            store.get("risk"),
            float(snapshot["account"]["equity"]) * reference["usd_cad"],
            maximum_drawdown=store.get("config")["policy"]["max_drawdown"],
        )
        store.observe(observation_time, snapshot, risk)
        halted = halted or risk["halted"]
    return submitted


def run_paper_cycle(workspace, *, broker=None, as_of=None, fx=None, market=None, refresh=True):
    """One restartable cycle. Injected broker/data are for isolated qualification tests."""
    owned = broker is None
    broker = broker or AlpacaPaper()
    try:
        with operator_lock(workspace):
            store = OperatorStore(workspace)
            try:
                config = store.get("config")
                if not config:
                    raise ValueError("Initialize a dedicated paper mandate before running cycles")
                if config["code_identity"] != operator_identity():
                    raise ValueError(
                        "Operator code changed; frozen mandate requires version migration"
                    )
                _reconcile(store, broker)
                snapshot = broker.snapshot()
                timestamp = as_of or _now()
                _validate_snapshot(snapshot, config["account_id"], timestamp)
                store.observe(timestamp, snapshot)
                balance = _balances(store, snapshot, timestamp)
                store.set("position_state", _position_state(store, snapshot["positions"]))
                reference = fx or fx_reference(workspace, timestamp)
                snapshot["fx"] = reference
                policy = SwingPolicy.model_validate(config["policy"])
                risk = update_risk(
                    store.get("risk"),
                    float(snapshot["account"]["equity"]) * reference["usd_cad"],
                    maximum_drawdown=policy.max_drawdown,
                )
                store.observe(timestamp, snapshot, risk)
                paused = store.get("paused", False)
                if risk["halted"] or paused:
                    for record in store.orders():
                        if (
                            record["payload"]["side"] == "buy"
                            and record["state"] == "BROKER"
                            and record["broker"]["status"] not in TERMINAL
                        ):
                            broker.cancel(record["broker"]["id"])
                    for record in store.orders():
                        if record["state"] == "PLANNED" and record["payload"]["side"] == "buy":
                            store.update_order(
                                record["id"], "SKIPPED", error="Paused or risk halted"
                            )
                outstanding = any(
                    r["state"] == "BROKER" and r["broker"]["status"] not in TERMINAL
                    for r in store.orders()
                )
                working_symbols = {
                    r["payload"]["symbol"]
                    for r in store.orders()
                    if r["state"] == "PLANNED"
                    or (r["state"] == "BROKER" and r["broker"]["status"] not in TERMINAL)
                }
                uncovered = [p for p in snapshot["positions"] if p["symbol"] not in working_symbols]
                if risk["halted"] and uncovered:
                    cal = xcals.get_calendar("XNYS")
                    next_open = pd.Timestamp(snapshot["clock"]["next_open"])
                    eligible = (
                        pd.Timestamp(timestamp) if snapshot["clock"]["is_open"] else next_open
                    )
                    session = eligible.tz_convert("America/New_York").date().isoformat()
                    emergency = {
                        "decision_at": timestamp,
                        "eligible_at": eligible.isoformat(),
                        "expires_at": cal.session_close(session).isoformat(),
                        "source_session": session,
                        "regime": "risk_halted",
                        "decisions": [],
                        "intents": [
                            {
                                "symbol": p["symbol"],
                                "side": "sell",
                                "qty": int(float(p["qty"])),
                                "type": "market",
                                "time_in_force": "day",
                                "reason": "30% sampled CAD drawdown breach",
                            }
                            for p in uncovered
                        ],
                    }
                    journal_key = hashlib.sha256(
                        encode(
                            [
                                [(p["symbol"], p["qty"]) for p in uncovered],
                                [
                                    (r["id"], r["state"], (r["broker"] or {}).get("status"))
                                    for r in store.orders()
                                    if r["payload"]["side"] == "sell"
                                ],
                            ]
                        ).encode()
                    ).hexdigest()[:16]
                    _save_plan(
                        store,
                        "halt-" + session + "-" + journal_key,
                        emergency,
                        {"source": "broker risk observation"},
                    )
                submitted = _submit_due(store, broker, snapshot, as_of, risk["halted"] or paused)
                if submitted:
                    _reconcile(store, broker)
                    snapshot = broker.snapshot()
                    timestamp = as_of or _now()
                    _validate_snapshot(snapshot, config["account_id"], timestamp)
                    balance = _balances(store, snapshot, timestamp)
                    snapshot["fx"] = reference
                    risk = store.get("risk")
                    store.observe(timestamp, snapshot)
                    store.set("position_state", _position_state(store, snapshot["positions"]))
                if not risk["halted"] and not outstanding and not snapshot["clock"]["is_open"]:
                    # Never create overlapping plans while earlier intents are working or queued.
                    pending = any(
                        r["state"] in {"PLANNED", "SUBMITTING", "UNKNOWN"}
                        or (r["state"] == "BROKER" and r["broker"]["status"] not in TERMINAL)
                        for r in store.orders()
                    )
                    cal = xcals.get_calendar("XNYS")
                    closed = cal.schedule.loc[
                        cal.schedule["close"] + pd.Timedelta(minutes=1) <= pd.Timestamp(timestamp)
                    ]
                    source_session = closed.index[-1].date().isoformat()
                    with store.connect() as connection:
                        planned = connection.execute(
                            "SELECT 1 FROM cycles WHERE session=?", (source_session,)
                        ).fetchone()
                    if not pending and not planned:
                        if market is None:
                            manifest, _ = capture_universe(
                                workspace, config["universe"], refresh=refresh
                            )
                            frame = read_capture(workspace, manifest)
                            capture = {
                                "capture_id": manifest["capture_id"],
                                "captured_at": manifest["captured_at"],
                            }
                        else:
                            frame, capture = market
                        decision_time = as_of or _now()
                        plan = plan_portfolio(
                            frame,
                            config["universe"],
                            as_of=decision_time,
                            positions=snapshot["positions"],
                            position_state=_position_state(store, snapshot["positions"]),
                            equity_usd=float(snapshot["account"]["equity"]),
                            spendable_usd=balance["spendable"],
                            policy=policy,
                            risk_halted=False,
                        )
                        if paused:
                            plan["intents"] = [i for i in plan["intents"] if i["side"] == "sell"]
                            for decision in plan["decisions"]:
                                if decision["action"] == "buy":
                                    decision.update(action="wait", reason="New entries are paused")
                        session_key = plan["source_session"]
                        if not plan.get("entry_data_complete", True):
                            session_key = "data-" + session_key + "-" + capture["capture_id"]
                        _save_plan(store, session_key, plan, capture)
                store.set(
                    "status",
                    {
                        "status": "risk_halted"
                        if risk["halted"]
                        else "paused"
                        if paused
                        else "ready",
                        "message": "Paper cycle reconciled; saved decisions await execution."
                        if not risk["halted"]
                        else "CAD drawdown limit reached; new exposure stopped and exits managed.",
                    },
                )
                return operator_status(workspace)
            except Exception as exc:
                # Persist sanitized local/broker errors; transport never includes response secrets.
                store.set("status", {"status": "recovery_required", "message": str(exc)})
                raise
    finally:
        if owned:
            broker.close()


def record_paper_flow(workspace, event_id, amount_usd, *, broker=None, as_of=None, fx=None):
    """Record an already observed simulator funding change, never transfer money."""
    if not event_id or not math.isfinite(amount_usd) or amount_usd == 0:
        raise ValueError("Funding needs a distinct event ID and finite nonzero amount")
    owned = broker is None
    broker = broker or AlpacaPaper()
    try:
        with operator_lock(workspace):
            store = OperatorStore(workspace)
            if any(row["id"] == event_id for row in store.flows()):
                raise ValueError("Funding event ID already recorded")
            config = store.get("config")
            if not config:
                raise ValueError("Initialize the paper mandate first")
            _reconcile(store, broker)
            snapshot = broker.snapshot()
            timestamp = as_of or _now()
            _validate_snapshot(snapshot, config["account_id"], timestamp)
            _balances(store, snapshot, timestamp, declared_flow=amount_usd)
            reference = fx or fx_reference(workspace, timestamp)
            snapshot["fx"] = reference
            risk = update_risk(
                store.get("risk"),
                float(snapshot["account"]["equity"]) * reference["usd_cad"],
                flow_cad=amount_usd * reference["usd_cad"],
                maximum_drawdown=config["policy"]["max_drawdown"],
            )
            with store.connect() as connection:
                connection.execute(
                    "INSERT INTO flows VALUES (?,?,?,?)",
                    (event_id, timestamp, amount_usd, encode(snapshot)),
                )
                for key, value in (("risk", risk), ("snapshot", snapshot)):
                    connection.execute(
                        "INSERT OR REPLACE INTO state VALUES (?,?)", (key, encode(value))
                    )
            return operator_status(workspace)
    finally:
        if owned:
            broker.close()


def pause_paper(workspace, paused=True):
    with operator_lock(workspace):
        store = OperatorStore(workspace)
        if not store.get("config"):
            raise ValueError("Paper mandate is not initialized")
        store.set("paused", paused)
        store.set(
            "status",
            {
                "status": "paused" if paused else "ready",
                "message": "Pause updated. Next cycle reconciles and cancels pending buys.",
            },
        )
    return operator_status(workspace)


def watch_paper(workspace, interval_seconds=300):
    """Run the same durable cycle unattended while this process/host remains awake."""
    import time

    if interval_seconds < 30:
        raise ValueError("Daily/weekly operation needs no sub-30-second polling")
    if not operator_status(workspace)["initialized"]:
        raise ValueError("Initialize the dedicated paper mandate before starting its runner")
    while True:
        try:
            state = run_paper_cycle(workspace)
            output = {
                "at": _now(),
                "status": state["status"],
                "message": state["message"],
                "orders": len(state["orders"]),
            }
        except Exception as exc:
            output = {"at": _now(), "status": "recovery_required", "message": str(exc)}
        print(encode(output), flush=True)
        time.sleep(interval_seconds)
