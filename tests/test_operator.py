"""Exercise complete paper lifecycles without credentials or financial transactions."""

import copy
import json
import subprocess
import sys

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import pytest

from frontier.operator import (
    _position_state,
    initialize_paper,
    operator_status,
    pause_paper,
    record_paper_flow,
    run_paper_cycle,
)
from frontier.operator_store import OperatorStore, operator_lock
from frontier.paper_broker import SubmissionUncertain

UNIVERSE = [
    {
        "symbol": "SPY",
        "currency": "USD",
        "calendar": "XNYS",
        "asset_type": "etf",
        "group": "market",
    },
    {
        "symbol": "AAA",
        "currency": "USD",
        "calendar": "XNYS",
        "asset_type": "stock",
        "group": "first",
    },
]
FX = {"usd_cad": 1.0, "available_at": "2026-09-18T20:30:00Z", "source": "test fixture"}
CALENDAR = xcals.get_calendar("XNYS")


def market(session="2026-09-18", *, drop=False):
    days = CALENDAR.sessions_window(session, -201)
    records = []
    for symbol, scale in (("AAA", 1), ("SPY", 10)):
        for index, day in enumerate(days):
            price = (20 + 0.035 * index + np.sin(index) * 0.1) * scale
            if drop and symbol == "AAA" and index == len(days) - 1:
                price *= 0.65
            records.append(
                {
                    "symbol": symbol,
                    "session": str(day.date()),
                    "available_at": CALENDAR.session_close(day) + pd.Timedelta(minutes=1),
                    "close": price,
                    "adjusted_close": price,
                    "high": price + 0.2 * scale,
                    "low": price - 0.2 * scale,
                    "volume": 5_000_000,
                }
            )
    return pd.DataFrame(records), {
        "capture_id": "synthetic-" + session,
        "source": "test-only fixture, not market evidence",
    }


class PaperSimulator:
    """Explicit broker double. Only fill() creates simulated holdings and cash."""

    def __init__(self, cash=700):
        self.cash = cash
        self.positions = {}
        self.orders = {}
        self.posts = []
        self.cancels = []
        self.timestamp = "2026-09-18T21:00:00Z"
        self.lose_response = False
        self.hide_lookup = False

    def snapshot(self):
        stamp = pd.Timestamp(self.timestamp)
        sessions = CALENDAR.sessions_in_range(stamp.date(), stamp.date() + pd.Timedelta(days=7))
        opens = [CALENDAR.session_open(day) for day in sessions]
        next_open = next(value for value in opens if value > stamp)
        is_open = any(
            CALENDAR.session_open(day) <= stamp < CALENDAR.session_close(day) for day in sessions
        )
        positions = [
            {
                "symbol": symbol,
                "qty": str(value["qty"]),
                "avg_entry_price": str(value["cost"]),
                "market_value": str(value["qty"] * value["mark"]),
                "asset_class": "us_equity",
            }
            for symbol, value in self.positions.items()
        ]
        return {
            "account": {
                "id": "dedicated-paper",
                "currency": "USD",
                "status": "ACTIVE",
                "trading_blocked": False,
                "cash": str(self.cash),
                "equity": str(self.cash + sum(float(p["market_value"]) for p in positions)),
                "buying_power": "999999",
            },
            "positions": positions,
            "orders": [
                copy.deepcopy(o)
                for o in self.orders.values()
                if o["status"] not in {"filled", "canceled", "expired", "rejected"}
            ],
            "clock": {
                "timestamp": self.timestamp,
                "is_open": is_open,
                "next_open": next_open.isoformat(),
            },
        }

    def get_order(self, identity):
        return None if self.hide_lookup else copy.deepcopy(self.orders.get(identity))

    def asset(self, symbol):
        return {"symbol": symbol, "status": "active", "tradable": True}

    def submit(self, payload):
        self.posts.append(copy.deepcopy(payload))
        identity = payload["client_order_id"]
        assert identity not in self.orders, "Duplicate paper submission"
        order = {
            **payload,
            "id": identity,
            "filled_qty": "0",
            "filled_avg_price": None,
            "status": "new",
            "updated_at": self.timestamp,
        }
        self.orders[identity] = order
        if self.lose_response:
            self.lose_response = False
            raise SubmissionUncertain("simulated lost response")
        return copy.deepcopy(order)

    def cancel(self, identity):
        self.cancels.append(identity)
        self.orders[identity]["status"] = "canceled"

    def fill(self, identity, *, quantity=None, price=27.0):
        order = self.orders[identity]
        total = float(order["qty"]) if quantity is None else quantity
        previous = float(order["filled_qty"])
        added = total - previous
        sign = 1 if order["side"] == "buy" else -1
        self.cash -= added * price * sign
        holding = self.positions.setdefault(
            order["symbol"], {"qty": 0, "cost": price, "mark": price}
        )
        holding["qty"] += added * sign
        if not holding["qty"]:
            del self.positions[order["symbol"]]
        order.update(
            filled_qty=str(total),
            filled_avg_price=str(price),
            status="filled" if total == float(order["qty"]) else "partially_filled",
            updated_at=self.timestamp,
            filled_at=self.timestamp if total == float(order["qty"]) else None,
        )


@pytest.fixture
def setup(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/scanner_universe.json").write_text(json.dumps(UNIVERSE), "utf-8")
    broker = PaperSimulator()
    initialize_paper(tmp_path, "dedicated-paper", 700, broker=broker, as_of=broker.timestamp, fx=FX)
    return tmp_path, broker


def cycle(setup, timestamp=None, session="2026-09-18", **kwargs):
    workspace, broker = setup
    if timestamp:
        broker.timestamp = timestamp
    return run_paper_cycle(
        workspace, broker=broker, as_of=broker.timestamp, fx=FX, market=market(session, **kwargs)
    )


def plan_and_submit(setup):
    plan = cycle(setup)
    assert plan["orders"] and not setup[1].posts
    return cycle(setup, "2026-09-21T14:00:00Z")


def test_saved_close_decision_submits_once_after_next_open_and_survives_restart(setup):
    workspace, broker = setup
    planned = cycle(setup)
    assert planned["orders"][0]["state"] == "PLANNED"
    assert planned["orders"][0]["eligible_at"].startswith("2026-09-21T13:30")
    cycle(setup, "2026-09-21T13:00:00Z")
    assert not broker.posts
    cycle(setup, "2026-09-21T14:00:00Z")
    cycle(setup, "2026-09-21T14:01:00Z")
    assert len(broker.posts) == 1
    assert OperatorStore(workspace).orders()[0]["state"] == "BROKER"
    broker.fill(broker.posts[0]["client_order_id"])
    state = cycle(setup, "2026-09-21T21:00:00Z", session="2026-09-21")
    assert state["account"]["last_snapshot"]["positions"][0]["symbol"] == "AAA"
    assert state["orders"][0]["broker"]["status"] == "filled"
    assert OperatorStore(workspace).get("position_state")["AAA"]["entry_session"] == "2026-09-21"
    assert len(broker.posts) == 1


def test_lost_submit_response_is_looked_up_not_resent(setup):
    workspace, broker = setup
    cycle(setup)
    broker.lose_response = True
    with pytest.raises(ValueError, match="uncertain"):
        cycle(setup, "2026-09-21T14:00:00Z")
    assert operator_status(workspace)["status"] == "recovery_required"
    assert OperatorStore(workspace).orders()[0]["state"] == "UNKNOWN"
    cycle(setup, "2026-09-21T14:01:00Z")
    assert len(broker.posts) == 1
    assert OperatorStore(workspace).orders()[0]["state"] == "BROKER"


def test_crash_before_submission_cannot_blindly_retry_unknown_outcome(setup):
    workspace, broker = setup
    record = cycle(setup)["orders"][0]
    OperatorStore(workspace).update_order(record["id"], "SUBMITTING")
    with pytest.raises(ValueError, match="Unresolved"):
        cycle(setup, "2026-09-21T14:00:00Z")
    assert not broker.posts
    assert OperatorStore(workspace).orders()[0]["state"] == "UNKNOWN"


def test_unmanaged_cash_blocks_orders_until_unique_explicit_funding_record(setup):
    workspace, broker = setup
    broker.cash += 700
    with pytest.raises(ValueError, match="cash change"):
        cycle(setup)
    state = record_paper_flow(
        workspace, "september-paper-addition", 700, broker=broker, as_of=broker.timestamp, fx=FX
    )
    assert state["account"]["risk"]["unit_nav"] == 1
    assert state["account"]["risk"]["units"] == 1400
    with pytest.raises(ValueError, match="already recorded"):
        record_paper_flow(
            workspace, "september-paper-addition", 700, broker=broker, as_of=broker.timestamp, fx=FX
        )
    assert not broker.posts


def test_expired_entry_is_not_submitted_late(setup):
    cycle(setup)
    state = cycle(setup, "2026-09-21T21:00:00Z", session="2026-09-21")
    assert state["orders"][0]["state"] == "SKIPPED"
    assert not setup[1].posts


def test_partial_fill_reconciles_then_daily_exit_uses_only_actual_shares(setup):
    workspace, broker = setup
    plan_and_submit(setup)
    identity = broker.posts[0]["client_order_id"]
    broker.fill(identity, quantity=1)
    state = cycle(setup, "2026-09-21T14:01:00Z")
    assert state["account"]["last_snapshot"]["positions"][0]["qty"] == "1.0"
    broker.cancel(identity)
    state = cycle(setup, "2026-09-22T21:00:00Z", session="2026-09-22", drop=True)
    sells = [o for o in state["orders"] if o["payload"]["side"] == "sell"]
    assert len(sells) == 1 and sells[0]["payload"]["qty"] == 1
    cycle(setup, "2026-09-23T14:00:00Z", session="2026-09-22", drop=True)
    assert len(broker.posts) == 2 and broker.posts[-1]["side"] == "sell"
    broker.fill(broker.posts[-1]["client_order_id"], price=18)
    state = cycle(setup, "2026-09-23T21:00:00Z", session="2026-09-23")
    assert not state["account"]["last_snapshot"]["positions"]
    assert OperatorStore(workspace).get("position_state") == {}


def test_pause_cancels_buys_but_continues_daily_exits(setup):
    workspace, broker = setup
    plan_and_submit(setup)
    broker.fill(broker.posts[0]["client_order_id"], quantity=1)
    pause_paper(workspace)
    state = cycle(setup, "2026-09-21T14:01:00Z")
    assert broker.cancels and state["status"] == "paused"
    state = cycle(setup, "2026-09-22T21:00:00Z", session="2026-09-22", drop=True)
    assert any(o["payload"]["side"] == "sell" for o in state["orders"])
    cycle(setup, "2026-09-23T14:00:00Z", session="2026-09-22", drop=True)
    assert broker.posts[-1]["side"] == "sell"


def test_drawdown_halt_cannot_be_cleared_by_resume_and_manages_after_hours_exit(setup):
    workspace, broker = setup
    plan_and_submit(setup)
    broker.fill(broker.posts[0]["client_order_id"])
    cycle(setup, "2026-09-21T14:01:00Z")
    # A CAD FX shock crosses30% even with a modest stock allocation; no invented cash loss.
    broker.timestamp = "2026-09-21T21:00:00Z"
    state = run_paper_cycle(
        workspace,
        broker=broker,
        as_of=broker.timestamp,
        fx={**FX, "usd_cad": 0.69},
        market=market("2026-09-21"),
    )
    assert state["status"] == "risk_halted"
    assert state["orders"][-1]["payload"]["side"] == "sell"
    pause_paper(workspace, paused=False)
    broker.timestamp = "2026-09-22T14:00:00Z"
    state = run_paper_cycle(
        workspace,
        broker=broker,
        as_of=broker.timestamp,
        fx={**FX, "usd_cad": 0.69},
        market=market("2026-09-21"),
    )
    assert state["account"]["risk"]["halted"]
    assert len(broker.posts) == 2 and broker.posts[-1]["side"] == "sell"


def test_broker_equity_and_account_mismatch_stop_the_cycle(setup):
    workspace, broker = setup
    original = broker.snapshot

    def wrong_account():
        snapshot = original()
        snapshot["account"]["id"] = "different-paper-account"
        return snapshot

    broker.snapshot = wrong_account
    with pytest.raises(ValueError, match="identity"):
        cycle(setup)
    assert not broker.posts


def test_operator_version_change_cannot_rewrite_frozen_plan(setup, monkeypatch):
    cycle(setup)
    monkeypatch.setattr("frontier.operator.operator_identity", lambda: "new-policy-identity")
    with pytest.raises(ValueError, match="code changed"):
        cycle(setup, "2026-09-21T14:00:00Z")
    assert not setup[1].posts


def test_reentered_symbol_uses_new_episode_not_old_buy(setup):
    workspace, _ = setup
    store = OperatorStore(workspace)
    for index, (side, day) in enumerate(
        (("buy", "2026-01-02"), ("sell", "2026-01-05"), ("buy", "2026-02-02"))
    ):
        plan = {"decision_at": day, "eligible_at": day, "expires_at": day}
        store.save_plan(
            day,
            day,
            plan,
            {},
            [{"id": str(index), "payload": {"symbol": "AAA", "side": side, "qty": 1}}],
        )
        store.update_order(
            str(index), "BROKER", {"filled_qty": "1", "filled_at": day + "T15:00:00Z"}
        )
    state = _position_state(store, [{"symbol": "AAA", "avg_entry_price": "20"}])
    assert state["AAA"]["entry_session"] == "2026-02-02"


def test_plan_and_peak_state_are_atomic_and_immutable(setup):
    workspace, _ = setup
    store = OperatorStore(workspace)
    plan = {
        "eligible_at": "future",
        "expires_at": "later",
        "next_position_state": {"AAA": {"peak_close": 100, "entry_session": "2026-09-01"}},
    }
    store.save_plan("test", "now", plan, {}, [{"id": "unique", "payload": {}}])
    assert store.get("position_state")["AAA"]["peak_close"] == 100
    changed = {**plan, "next_position_state": {}}
    assert not store.save_plan("test", "now", changed, {}, [])
    assert store.get("position_state")["AAA"]["peak_close"] == 100
    with pytest.raises(Exception):
        store.save_plan("failed", "now", changed, {}, [{"id": "unique", "payload": {}}])
    assert store.latest_cycle()["session"] == "test"
    assert store.get("position_state")["AAA"]["peak_close"] == 100


def test_native_lock_excludes_second_process_and_releases(setup):
    workspace, _ = setup
    code = (
        "from frontier.operator_store import operator_lock; import sys; "
        "guard=operator_lock(sys.argv[1]); guard.__enter__(); guard.__exit__(None,None,None)"
    )
    with operator_lock(workspace):
        result = subprocess.run([sys.executable, "-c", code, str(workspace)], capture_output=True)
        assert result.returncode != 0 and b"Another paper operator" in result.stderr
    result = subprocess.run([sys.executable, "-c", code, str(workspace)], capture_output=True)
    assert result.returncode == 0


def test_incomplete_capture_does_not_consume_the_completed_session_plan(setup):
    workspace, broker = setup
    frame, capture = market()
    stale = frame[~((frame.symbol == "AAA") & (frame.session == "2026-09-18"))]
    waiting = run_paper_cycle(
        workspace,
        broker=broker,
        as_of=broker.timestamp,
        fx=FX,
        market=(stale, {**capture, "capture_id": "incomplete"}),
    )
    assert not waiting["orders"]
    assert not waiting["latest_cycle"]["plan"]["entry_data_complete"]
    ready = cycle(setup)
    assert ready["latest_cycle"]["plan"]["entry_data_complete"]
    assert ready["orders"]


def test_immediate_fill_after_request_start_is_valid_at_fresh_observation(setup, monkeypatch):
    workspace, broker = setup
    cycle(setup)
    broker.timestamp = "2026-09-21T14:00:00Z"
    monkeypatch.setattr("frontier.operator._now", lambda: broker.timestamp)
    submit = broker.submit

    def immediate(payload):
        submit(payload)
        broker.timestamp = "2026-09-21T14:00:02Z"
        broker.fill(payload["client_order_id"])
        return broker.get_order(payload["client_order_id"])

    broker.submit = immediate
    state = run_paper_cycle(workspace, broker=broker, fx=FX, market=market())
    assert state["status"] == "ready" and state["orders"][0]["broker"]["status"] == "filled"
    assert "peak_close" not in OperatorStore(workspace).get("position_state")["AAA"]
    assert len(broker.posts) == 1


def test_rejected_exit_remains_visible_as_recovery_required(setup):
    workspace, broker = setup
    plan_and_submit(setup)
    broker.fill(broker.posts[0]["client_order_id"])
    cycle(setup, "2026-09-21T21:00:00Z", session="2026-09-21", drop=True)

    def reject(payload):
        raise RuntimeError("Paper broker HTTP429")

    broker.submit = reject
    with pytest.raises(ValueError, match="exit rejected"):
        cycle(setup, "2026-09-22T14:00:00Z", session="2026-09-21")
    with pytest.raises(ValueError, match="exit rejected"):
        cycle(setup, "2026-09-22T14:01:00Z", session="2026-09-21")
    assert operator_status(workspace)["status"] == "recovery_required"


def test_consecutive_immediate_fills_recheck_current_gross_exposure(setup):
    from frontier.operator import _save_plan, _submit_due

    workspace, broker = setup
    store = OperatorStore(workspace)
    config = store.get("config")
    config["initial_cash_usd"] = 1000
    store.set("config", config)
    broker.cash = 1000
    broker.timestamp = "2026-09-18T14:00:00Z"
    old = {
        "decision_at": broker.timestamp,
        "eligible_at": broker.timestamp,
        "expires_at": "2026-09-18T20:00:00Z",
        "intents": [
            {
                "symbol": "AAA",
                "side": "buy",
                "qty": 1,
                "type": "limit",
                "time_in_force": "day",
                "limit_price": "200",
            }
        ],
    }
    _save_plan(store, "previous", old, {})
    previous = store.orders()[0]
    broker.submit(previous["payload"])
    broker.fill(previous["id"], price=200)
    store.update_order(previous["id"], "BROKER", broker.get_order(previous["id"]))
    broker.positions["AAA"]["mark"] = 300
    broker.timestamp = "2026-09-21T14:00:00Z"
    plan = {
        **old,
        "decision_at": broker.timestamp,
        "eligible_at": broker.timestamp,
        "expires_at": "2026-09-21T20:00:00Z",
        "intents": [
            {
                "symbol": symbol,
                "side": "buy",
                "qty": 1,
                "type": "limit",
                "time_in_force": "day",
                "limit_price": "200",
            }
            for symbol in ("BBB", "CCC", "DDD")
        ],
    }
    _save_plan(store, "current", plan, {})
    submit = broker.submit

    def immediate(payload):
        submit(payload)
        broker.fill(payload["client_order_id"], price=200)
        return broker.get_order(payload["client_order_id"])

    broker.submit = immediate
    snapshot = broker.snapshot()
    snapshot["fx"] = FX
    _submit_due(store, broker, snapshot, broker.timestamp, False)
    assert len(broker.posts) == 3  # original holding plus two acceptable new positions
    assert store.orders()[-1]["state"] == "SKIPPED"
    assert "exposure cap" in store.orders()[-1]["error"]


def test_unattended_runner_reuses_cycle_and_stops_cleanly_on_interrupt(setup, monkeypatch, capsys):
    from frontier.operator import watch_paper

    calls = []

    def fake_cycle(workspace):
        calls.append(workspace)
        return {"status": "ready", "message": "fixture only", "orders": []}

    def interrupt_sleep(seconds):
        assert seconds == 300
        raise KeyboardInterrupt

    monkeypatch.setattr("frontier.operator.run_paper_cycle", fake_cycle)
    monkeypatch.setattr("time.sleep", interrupt_sleep)
    with pytest.raises(KeyboardInterrupt):
        watch_paper(setup[0])
    assert calls == [setup[0]]
    assert json.loads(capsys.readouterr().out)["status"] == "ready"


def test_nonatomic_rest_marks_do_not_falsely_fail_reconciliation(setup):
    from frontier.operator import _validate_snapshot

    _, broker = setup
    snapshot = broker.snapshot()
    snapshot["account"].update(cash="100", equity="200", long_market_value="100")
    snapshot["positions"] = [{"symbol": "AAA", "qty": "1", "market_value": "100.03"}]
    _validate_snapshot(snapshot, "dedicated-paper", broker.timestamp)
    snapshot["account"]["long_market_value"] = "105"
    with pytest.raises(ValueError, match="do not reconcile"):
        _validate_snapshot(snapshot, "dedicated-paper", broker.timestamp)


def test_one_unfilled_sell_does_not_prevent_other_drawdown_exits(setup):
    from frontier.operator import _save_plan

    workspace, broker = setup
    store = OperatorStore(workspace)
    broker.timestamp = "2026-09-18T14:00:00Z"
    plan = {
        "decision_at": broker.timestamp,
        "eligible_at": broker.timestamp,
        "expires_at": "2026-09-18T20:00:00Z",
        "intents": [
            {
                "symbol": symbol,
                "side": "buy",
                "qty": 1,
                "type": "limit",
                "time_in_force": "day",
                "limit_price": "100",
            }
            for symbol in ("AAA", "BBB")
        ],
    }
    _save_plan(store, "entries", plan, {})
    for record in store.orders():
        broker.submit(record["payload"])
        broker.fill(record["id"], price=100)
        store.update_order(record["id"], "BROKER", broker.get_order(record["id"]))
    broker.timestamp = "2026-09-21T14:00:00Z"
    plan = {
        **plan,
        "decision_at": broker.timestamp,
        "eligible_at": broker.timestamp,
        "expires_at": "2026-09-21T20:00:00Z",
        "intents": [
            {"symbol": "AAA", "side": "sell", "qty": 1, "type": "market", "time_in_force": "day"}
        ],
    }
    _save_plan(store, "first-exit", plan, {})
    sell = store.orders()[-1]
    store.update_order(sell["id"], "BROKER", broker.submit(sell["payload"]))
    for timestamp in ("2026-09-21T14:01:00Z", "2026-09-21T14:06:00Z"):
        broker.timestamp = timestamp
        state = run_paper_cycle(
            workspace, broker=broker, as_of=timestamp, fx={**FX, "usd_cad": 0.69}, market=market()
        )
        assert state["status"] == "risk_halted"
    sells = [p["symbol"] for p in broker.posts if p["side"] == "sell"]
    assert sells == ["AAA", "BBB"]
