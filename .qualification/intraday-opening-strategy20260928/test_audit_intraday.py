"""Synthetic audit checks; no historical accounts or strategy study execution."""
import copy
import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

audit = load("independent_intraday_audit", ROOT / "audit_intraday.py")
fixture = load("intraday_synthetic_fixtures", ROOT / "test_strategy.py")

class SyntheticSource:
    def __init__(self, sessions, rows):
        self.sessions, self.rows = sessions, rows
    def bars(self, index):
        return self.rows[index]
    def hour(self, index, symbol):
        return audit.opening(self.rows[index], symbol)

def verify(sessions, rows, report):
    settlements = audit.build_settlement_indices([s["session"] for s in sessions], "USD")
    return audit.audit_account(report, SyntheticSource(sessions, rows), settlements)

@pytest.mark.parametrize("profile", ["proportional", "moomoo_ca_us"])
def test_complete_fee_settlement_minute_nav_and_reference(profile):
    sessions, rows = fixture.fixture(exit_=10.4)
    report = fixture.run(sessions, rows, cost_profile=profile)
    result = verify(sessions, rows, report)
    assert result["audit_status"] == "passed_complete_ledger"
    assert result["checked_marks"] == len(report["intraday_equity"])
    assert result["completed_trades"] > 0

def test_invalid_entry_retains_existing_fill_and_suppresses_full_metrics():
    sessions, rows = fixture.fixture()
    del rows[20]["BANF"][76]
    report = fixture.run(sessions, rows)
    result = verify(sessions, rows, report)
    assert result["audit_status"] == "passed_invalid_prefix"
    assert not result["economic_metrics_valid"]

def test_missing_exit_and_sparse_minutes_remain_explicit():
    sessions, rows = fixture.fixture()
    del rows[20]["AAPL"][196]
    del rows[20]["MSFT"][101]
    rows[20]["AAPL"][100]["c"] = 5
    report = fixture.run(sessions, rows)
    result = verify(sessions, rows, report)
    assert result["audit_status"] == "passed_invalid_prefix"
    assert report["stale_mark_observations"] > 0

def test_zero_fill_cancellation_and_all_cash_account():
    sessions, rows = fixture.fixture(entry=1000)
    report = fixture.run(sessions, rows, cost_profile="moomoo_ca_us")
    result = verify(sessions, rows, report)
    assert result["completed_trades"] == 0 and result["ending_equity"] == 2000

@pytest.mark.parametrize("corruption", ["source_price", "reservation", "minute_nav", "period_return", "reference_return"])
def test_audit_rejects_economic_corruption(corruption):
    sessions, rows = fixture.fixture(exit_=10.4)
    report = fixture.run(sessions[:21], rows[:21])
    changed = copy.deepcopy(report)
    if corruption == "source_price": changed["trades"][0]["exit_price"] += .01
    elif corruption == "reservation": changed["orders"][0]["reserved_cash"] += 1
    elif corruption == "minute_nav": next(p for p in changed["intraday_equity"] if p["phase"] == "minute_close")["equity"] += 1
    elif corruption == "period_return": changed["monthly"][0]["return_"] += .01
    else: changed["event_reference"][0]["matched_events"][0]["gross_return"] += .01
    with pytest.raises(AssertionError): verify(sessions[:21], rows[:21], changed)

def test_exception_account_is_retained_without_qualified_metrics():
    result = audit.audit_account({"status": "failed", "error": "source identity changed"}, None, None)
    assert result["audit_status"] == "retained_exception_without_ledger"


def test_historical_t3_cash_availability_is_reconstructed():
    sessions = fixture.calendar("2017-01-03", count=23)
    rows = [fixture.bars(narrow=True) for _ in sessions]
    for day in rows[20:]:
        for symbol in fixture.strategy.STOCKS:
            for minute in range(60): day[symbol][minute]["v"] *= 2
    report = fixture.run(sessions, rows)
    result = verify(sessions, rows, report)
    assert result["audit_status"] == "passed_complete_ledger"
    assert report["daily_equity"][0]["unsettled_cash"] > 1500


def test_dropped_observed_minute_mark_is_rejected():
    sessions, rows = fixture.fixture()
    report = fixture.run(sessions[:21], rows[:21])
    first_minute = next(i for i,p in enumerate(report["intraday_equity"]) if p["phase"] == "minute_close")
    del report["intraday_equity"][first_minute]
    with pytest.raises(AssertionError, match="Every observed held-minute"):
        verify(sessions[:21], rows[:21], report)
