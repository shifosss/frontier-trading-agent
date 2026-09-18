import copy

import pandas as pd
import pytest

from frontier.data import import_dataset, load_dataset
from frontier.domain import RunConfig, StrategyConfig
from frontier.fixtures import generate_fixture
from frontier.replay import replay_dataset, run_research
from frontier.reports import write_report
from frontier.store import Registry


@pytest.fixture
def tiny(tmp_path):
    source = generate_fixture(tmp_path / "source")
    bars = pd.read_csv(source / "bars.csv")
    bars = bars.loc[bars.event_time.str[:10] <= "2025-01-06"].copy()
    bars[["open", "high", "low", "close"]] = 100
    bars.to_csv(source / "bars.csv", index=False)
    fx = pd.read_csv(source / "fx.csv")
    fx.usd_cad = 1.25
    fx.to_csv(source / "fx.csv", index=False)
    root = tmp_path / "datasets"
    manifest = import_dataset(source, root)
    return load_dataset(root, manifest.dataset_id), root


def config(dataset, **kwargs):
    return RunConfig(
        dataset_id=dataset.manifest.dataset_id,
        initial_cash_usd=1000,
        initial_cash_cad=1000,
        slippage_bps=0,
        **kwargs,
    )


def test_actual_engine_hand_accounting_and_next_open(tiny):
    dataset, _ = tiny
    result = replay_dataset(dataset, config(dataset))
    assert result["engine_identity"]["account_count"] == 1
    assert result["engine_identity"]["version"] == "1.231.0"
    assert result["balances"] == {"USD": 699, "CAD": 599}
    assert {p["currency"]: p["quantity"] for p in result["positions"]} == {"USD": 3, "CAD": 4}
    assert result["summary"]["initial_nav"] == 2250
    assert result["summary"]["final_nav"] == 2247.75
    assert result["summary"]["fees"] == {"USD": 1, "CAD": 1}
    assert len(result["fills"]) == 2
    for fill in result["fills"]:
        assert fill["price"] == 100
        assert fill["commission"] == 1
        assert fill["timestamp"] == "2025-01-03T14:30:00+00:00"
        assert pd.Timestamp(fill["timestamp"]) > pd.Timestamp(fill["decision_time"])
    for point in result["equity_curve"]:
        expected = (point["cash_usd"] + point["positions_value_usd"]) * point["usd_cad"]
        expected += point["cash_cad"] + point["positions_value_cad"]
        assert point["nav"] == pytest.approx(expected)
        assert point["cash_usd"] >= 0 and point["cash_cad"] >= 0


def test_equal_availability_open_is_not_eligible(tiny):
    dataset, _ = tiny
    dataset.bars.loc[dataset.bars.event_time.dt.day == 2, "available_at"] = pd.Timestamp(
        "2025-01-03T14:30:00Z"
    )
    result = replay_dataset(dataset, config(dataset))
    assert {f["timestamp"] for f in result["fills"]} == {"2025-01-06T14:30:00+00:00"}


def test_group_cap_separate_funding_and_pending(tiny):
    dataset, _ = tiny
    for instrument in dataset.manifest.instruments:
        instrument.exposure_group = "interlisted"
    result = replay_dataset(dataset, config(dataset, strategy=StrategyConfig(rebalance_every=1)))
    for point in result["equity_curve"]:
        assert point["gross_exposure"] <= 0.2
    assert len(result["unfilled_intents"]) == 2
    zero = replay_dataset(
        dataset,
        RunConfig(
            dataset_id=dataset.manifest.dataset_id,
            initial_cash_usd=1000,
            initial_cash_cad=0,
            slippage_bps=0,
        ),
    )
    assert zero["balances"]["CAD"] == 0
    assert all(fill["currency"] == "USD" for fill in zero["fills"])


def test_future_price_revision_and_fx_mutation_invariance(tiny):
    dataset, _ = tiny
    before = replay_dataset(dataset, config(dataset))
    later = copy.deepcopy(dataset)
    later.bars.loc[later.bars.event_time.dt.day == 6, ["open", "close", "high"]] *= 4
    revision = later.bars.iloc[[0]].copy()
    revision.available_at = pd.Timestamp("2025-01-06T22:00:00Z")
    revision[["open", "high", "low", "close"]] = 17
    later.bars = pd.concat([later.bars, revision], ignore_index=True)
    later.fx.loc[later.fx.available_at > pd.Timestamp("2025-01-04T00:00Z"), "usd_cad"] = 3
    after = replay_dataset(later, config(later))
    cutoff = "2025-01-04"
    for field, time_key in (
        ("fills", "timestamp"),
        ("decisions", "decision_time"),
        ("equity_curve", "timestamp"),
    ):
        assert [x for x in before[field] if x[time_key] < cutoff] == [
            x for x in after[field] if x[time_key] < cutoff
        ]


def test_cash_repeat_zero_variance_and_missing_fx(tiny):
    dataset, _ = tiny
    cfg = config(dataset, strategy=StrategyConfig(family="cash"))
    result = replay_dataset(dataset, cfg)
    assert result == replay_dataset(dataset, cfg)
    assert result["fills"] == []
    assert result["summary"]["sharpe"] is None
    assert result["summary"]["annualized_volatility"] is None
    dataset.fx = dataset.fx.iloc[0:0]
    with pytest.raises(ValueError, match="published FX"):
        replay_dataset(dataset, cfg)


def test_actions_incomplete_explicit_and_failure_persistence(tiny, tmp_path):
    dataset, root = tiny
    dataset.actions = pd.DataFrame([{"type": "split"}])
    with pytest.raises(ValueError, match="Stock splits"):
        replay_dataset(dataset, config(dataset))
    dataset.actions = dataset.actions.iloc[0:0]
    dataset.manifest.corporate_actions_status = "unknown"
    with pytest.raises(ValueError, match="explicit"):
        replay_dataset(dataset, config(dataset))
    result = replay_dataset(dataset, config(dataset, allow_incomplete_actions=True))
    assert result["summary"]["total_return"] is None
    assert result["summary"]["raw_price_return"] < 0
    registry = Registry(tmp_path / "registry.sqlite")
    missing = RunConfig(dataset_id="0" * 64)
    with pytest.raises(FileNotFoundError):
        run_research(missing, root, registry, tmp_path / "artifacts")
    assert registry.list_runs()[0]["status"] == "FAILED"


def test_holiday_specific_next_open(tmp_path):
    source = generate_fixture(tmp_path / "source")
    bars = pd.read_csv(source / "bars.csv")
    bars = bars.loc[bars.event_time.str[:10].between("2025-06-30", "2025-07-07")]
    bars.to_csv(source / "bars.csv", index=False)
    manifest = import_dataset(source, tmp_path / "datasets")
    dataset = load_dataset(tmp_path / "datasets", manifest.dataset_id)
    result = replay_dataset(dataset, config(dataset))
    initial = {fill["currency"]: fill["timestamp"] for fill in result["fills"]}
    assert initial["USD"].startswith("2025-07-01")
    assert initial["CAD"].startswith("2025-07-02")


def test_hourly_signal_uses_next_strictly_later_hour_open(tiny):
    dataset, _ = tiny
    dataset.manifest.interval = "1h"
    rows = []
    for key in dataset.bars.instrument_id.unique():
        template = dataset.bars.loc[dataset.bars.instrument_id == key].iloc[0].copy()
        for hour in (15, 16, 17):
            row = template.copy()
            row.event_time = pd.Timestamp(f"2025-01-02T{hour}:30:00Z")
            row.available_at = row.event_time + pd.Timedelta(minutes=1)
            rows.append(row)
    dataset.bars = pd.DataFrame(rows)
    result = replay_dataset(dataset, config(dataset))
    assert len(result["fills"]) == 2
    assert {fill["timestamp"] for fill in result["fills"]} == {"2025-01-02T16:30:00+00:00"}
    assert all(fill["decision_time"] == "2025-01-02T15:31:00+00:00" for fill in result["fills"])


def test_downward_opening_gap_cannot_overallocate_close_marked_nav(tiny):
    dataset, _ = tiny
    dataset.bars.loc[dataset.bars.event_time.dt.day == 3, "open"] = 10
    result = replay_dataset(dataset, config(dataset))
    assert all(point["gross_exposure"] <= 0.4 for point in result["equity_curve"])


def test_slippage_is_separate_actual_fill_cost(tiny):
    dataset, _ = tiny
    cfg = RunConfig(
        dataset_id=dataset.manifest.dataset_id,
        initial_cash_usd=1000,
        initial_cash_cad=1000,
        slippage_bps=100,
    )
    result = replay_dataset(dataset, cfg)
    assert {fill["price"] for fill in result["fills"]} == {101}
    assert result["balances"] == {"USD": 696, "CAD": 595}
    assert result["summary"]["slippage"] == {"USD": 3, "CAD": 4}
    assert result["summary"]["final_nav"] == 2240


def test_known_dividend_failure_is_durable(tiny, tmp_path):
    dataset, root = tiny
    source = tmp_path / "source"
    pd.DataFrame(
        [
            {
                "instrument_id": "FICTUS.XNYS",
                "event_time": "2025-01-03T14:30:00Z",
                "available_at": "2025-01-03T14:30:00Z",
                "type": "dividend",
                "cash_amount": 0.5,
                "currency": "USD",
                "ratio": None,
            }
        ]
    ).to_csv(source / "actions.csv", index=False)
    manifest = import_dataset(source, root)
    registry = Registry(tmp_path / "action-registry.sqlite")
    with pytest.raises(ValueError, match="require payable_at"):
        run_research(
            RunConfig(dataset_id=manifest.dataset_id, allow_incomplete_actions=True),
            root,
            registry,
            tmp_path / "artifacts",
        )
    failed = registry.list_runs()[0]
    assert failed["status"] == "FAILED"
    assert "require payable_at" in failed["error"]


def test_market_attribution_retains_reopened_lifecycles_and_cash_rounding(tmp_path):
    source = generate_fixture(tmp_path / "source")
    root = tmp_path / "datasets"
    manifest = import_dataset(source, root)
    dataset = load_dataset(root, manifest.dataset_id)
    dataset.manifest.instruments = [i for i in dataset.manifest.instruments if i.currency == "USD"]
    bars = dataset.bars.loc[dataset.bars.instrument_id == "FICTUS.XNYS"].iloc[:10].copy()
    bars["close"] = [100, 110, 90, 110, 90, 110, 90, 110, 90, 110]
    bars["open"] = [
        100,
        100,
        100.1234,
        101.4567,
        100.1234,
        101.4567,
        100.1234,
        101.4567,
        100.1234,
        101.4567,
    ]
    bars["high"], bars["low"] = 111, 89
    dataset.bars = bars
    cfg = RunConfig(
        dataset_id=manifest.dataset_id,
        base_currency="USD",
        initial_cash_usd=1000,
        initial_cash_cad=0,
        slippage_bps=0,
        strategy=StrategyConfig(family="trend", lookback=2, rebalance_every=1),
    )
    result = replay_dataset(dataset, cfg)
    assert [fill["side"] for fill in result["fills"]] == ["BUY", "SELL"] * 4
    assert all(fill["quantity"] == 1 for fill in result["fills"])
    # Each round trip: rounded engine cash +101.46 -100.12 -2 fees = -0.66.
    assert result["positions"] == []
    assert result["balances"]["USD"] == 997.36
    assert result["summary"]["per_market_contribution"]["XNYS"]["USD"] == -2.64
    for currency, native in result["summary"]["native_market_contribution"].items():
        attributed = sum(v[currency] for v in result["summary"]["per_market_contribution"].values())
        assert attributed == pytest.approx(native)


@pytest.mark.parametrize("paid", [True, False])
def test_dividend_receivable_native_cash_and_market_contribution(tiny, paid):
    dataset, root = tiny
    later = dataset.bars.loc[dataset.bars.event_time.dt.day == 6].copy()
    later["event_time"] += pd.Timedelta(days=1)
    later["available_at"] += pd.Timedelta(days=1)
    dataset.bars = pd.concat([dataset.bars, later], ignore_index=True)
    dataset.bars.loc[dataset.bars.event_time.dt.day >= 6, ["open", "high", "low", "close"]] = 99
    payable = pd.Timestamp("2025-01-07T01:00Z" if paid else "2025-01-10T01:00Z")
    dataset.actions = pd.DataFrame(
        [
            {
                "instrument_id": i.id,
                "event_time": pd.Timestamp("2025-01-06T14:30Z"),
                "available_at": pd.Timestamp("2025-01-06T14:30Z"),
                "type": "dividend",
                "cash_amount": 1.0,
                "currency": i.currency,
                "ratio": None,
                "payable_at": payable,
            }
            for i in dataset.manifest.instruments
        ]
    )
    dataset.manifest.corporate_actions_status = "unknown"
    result = replay_dataset(
        dataset, config(dataset, commission_per_order=0, allow_incomplete_actions=True)
    )
    assert result["summary"]["total_return"] is None
    report = write_report(result, root / "dividend-report.html").read_text("utf-8")
    assert "Raw prices plus recorded gross cash dividends" in report
    assert "action coverage is incomplete" in report
    assert "Dividend Receivables" in report
    assert result["summary"]["final_nav"] == 2250
    assert all(point["nav"] == 2250 for point in result["equity_curve"])
    assert result["summary"]["dividend_income"] == {"USD": 3, "CAD": 4}
    assert result["summary"]["native_market_contribution"] == {"USD": 0, "CAD": 0}
    assert result["summary"]["per_market_contribution"] == {
        "XNYS": {"USD": 0, "CAD": 0},
        "XTSE": {"USD": 0, "CAD": 0},
    }
    assert result["summary"]["return_basis"] == "raw_price_plus_gross_cash_dividends"
    assert result["balances"] == ({"USD": 703, "CAD": 604} if paid else {"USD": 700, "CAD": 600})
    assert result["dividend_receivables"] == (
        {"USD": 0, "CAD": 0} if paid else {"USD": 3, "CAD": 4}
    )
    assert {entry["paid_at"] for entry in result["dividends"]} == {
        "2025-01-07T14:30:00+00:00" if paid else None
    }
    # There is no quote at the payment timestamp; cash cannot be spent before it.
    before_payment = [p for p in result["equity_curve"] if p["timestamp"] < payable.isoformat()]
    assert all(p["cash_usd"] == 700 for p in before_payment if p["dividend_receivable_usd"])


@pytest.mark.parametrize("ex_day, expected_entitlement", [(6, 0), (7, 3)])
def test_dividend_ex_date_seller_keeps_entitlement_and_buyer_does_not(
    tiny, ex_day, expected_entitlement
):
    dataset, _ = tiny
    dataset.manifest.instruments = [i for i in dataset.manifest.instruments if i.currency == "USD"]
    bars = dataset.bars.loc[dataset.bars.instrument_id == "FICTUS.XNYS"].copy()
    later = bars.iloc[[-1]].copy()
    later["event_time"] += pd.Timedelta(days=1)
    later["available_at"] += pd.Timedelta(days=1)
    bars = pd.concat([bars, later], ignore_index=True)
    bars["close"] = [100, 110, 90, 89]
    bars["open"] = [100, 100, 100, 89]
    bars["high"], bars["low"] = 111, 88
    dataset.bars = bars
    ex_time = pd.Timestamp(f"2025-01-{ex_day:02}T14:30Z")
    dataset.actions = pd.DataFrame(
        [
            {
                "instrument_id": "FICTUS.XNYS",
                "event_time": ex_time,
                "available_at": ex_time,
                "type": "dividend",
                "cash_amount": 1.0,
                "currency": "USD",
                "ratio": None,
                "payable_at": pd.Timestamp("2025-01-10T01:00Z"),
            }
        ]
    )
    result = replay_dataset(
        dataset,
        config(
            dataset,
            commission_per_order=0,
            strategy=StrategyConfig(family="trend", lookback=2, rebalance_every=1),
        ),
    )
    assert result["dividends"][0]["quantity"] == expected_entitlement
    assert [(f["timestamp"][:10], f["side"]) for f in result["fills"]] == [
        ("2025-01-06", "BUY"),
        ("2025-01-07", "SELL"),
    ]
    assert result["dividend_receivables"]["USD"] == expected_entitlement
    assert result["positions"] == []


def test_dividend_revisions_and_late_availability_are_rejected(tiny):
    dataset, _ = tiny
    event = pd.Timestamp("2025-01-06T14:30Z")
    row = {
        "instrument_id": "FICTUS.XNYS",
        "event_time": event,
        "available_at": event,
        "type": "dividend",
        "cash_amount": 1.0,
        "currency": "USD",
        "ratio": None,
        "payable_at": pd.Timestamp("2025-01-10T01:00Z"),
    }
    dataset.actions = pd.DataFrame([row, row])
    with pytest.raises(ValueError, match="Revised dividend"):
        replay_dataset(dataset, config(dataset))
    dataset.actions = pd.DataFrame([{**row, "available_at": event + pd.Timedelta(hours=1)}])
    with pytest.raises(ValueError, match="Late dividend"):
        replay_dataset(dataset, config(dataset))
