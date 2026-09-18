import json
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from frontier.data import as_of, fx_as_of, import_dataset, list_datasets, load_dataset
from frontier.domain import Instrument, RunConfig, StrategyConfig

INSTRUMENTS = [
    dict(
        id="FICTUS.XNYS",
        symbol="FICTUS",
        venue="XNYS",
        currency="USD",
        asset_type="stock",
        exposure_group="us",
    ),
    dict(
        id="FICTCA.XTSE",
        symbol="FICTCA",
        venue="XTSE",
        currency="CAD",
        asset_type="etf",
        exposure_group="ca",
    ),
]


def bar(instrument="FICTUS.XNYS", event="2025-07-02T20:00:00Z", **changes):
    row = dict(
        instrument_id=instrument,
        event_time=event,
        available_at=event,
        open=100,
        high=105,
        low=95,
        close=102,
        volume=1000,
    )
    row.update(changes)
    return row


def source(tmp_path, bars=None, actions=None, fx=None, **metadata):
    folder = tmp_path / "source"
    folder.mkdir(exist_ok=True)
    meta = dict(
        schema_version=1,
        name="Test fixture",
        mode="synthetic_fixture",
        source="test-v1",
        source_url="local:test",
        retrieved_at="2025-08-01T00:00:00Z",
        usage_notes="Fictional test data only",
        availability_basis="documented",
        adjustment_policy="raw",
        corporate_actions_status="complete",
        instruments=INSTRUMENTS,
        interval="1d",
        limitations=[],
    )
    meta.update(metadata)
    (folder / "dataset.json").write_text(json.dumps(meta), encoding="utf-8")
    pd.DataFrame(bars if bars is not None else [bar(), bar("FICTCA.XTSE")]).to_csv(
        folder / "bars.csv", index=False
    )
    if actions is not None:
        pd.DataFrame(actions).to_csv(folder / "actions.csv", index=False)
    if fx is not None:
        pd.DataFrame(fx).to_csv(folder / "fx.csv", index=False)
    return folder


def test_import_reimport_immutable_and_actual_duckdb(tmp_path):
    folder = source(tmp_path)
    root = tmp_path / "store with 'quote"
    first = import_dataset(folder, root)
    before = {p.name: p.read_bytes() for p in (root / first.dataset_id).glob("*") if p.is_file()}
    second = import_dataset(folder, root)
    assert first == second
    assert before == {
        p.name: p.read_bytes() for p in (root / first.dataset_id).glob("*") if p.is_file()
    }
    loaded = load_dataset(root, first.dataset_id)
    assert loaded.bars.close.tolist() == [102, 102]
    assert loaded.bars.ingested_at.nunique() == 1
    assert len(list_datasets(root)) == 1
    assert loaded.actions.empty and loaded.fx.empty
    # Identity distinguishes even source whitespace changes.
    with (folder / "dataset.json").open("a", encoding="utf-8") as stream:
        stream.write("\n")
    changed = import_dataset(folder, root)
    assert changed.dataset_id != first.dataset_id
    assert len(list_datasets(root)) == 2


def test_changed_prices_get_new_identity_and_original_survives(tmp_path):
    folder = source(tmp_path)
    root = tmp_path / "store"
    old = import_dataset(folder, root)
    frame = pd.read_csv(folder / "bars.csv")
    frame.loc[0, "close"] = 104
    frame.to_csv(folder / "bars.csv", index=False)
    new = import_dataset(folder, root)
    assert old.dataset_id != new.dataset_id
    assert 104 not in load_dataset(root, old.dataset_id).bars.close.tolist()
    assert 104 in load_dataset(root, new.dataset_id).bars.close.tolist()


def test_future_revision_cannot_rewrite_earlier_view(tmp_path):
    records = [
        bar(revision_id="original"),
        bar(close=104, available_at="2025-07-03T19:00:00Z", revision_id="correction"),
        bar(event="2025-07-03T17:00:00Z", close=103, revision_id="original"),
    ]
    folder = source(tmp_path, records)
    manifest = import_dataset(folder, tmp_path / "store")
    frame = load_dataset(tmp_path / "store", manifest.dataset_id).bars
    early = as_of(frame, "2025-07-02T21:00:00Z")
    assert early.close.tolist() == [102]
    mutated = frame.copy()
    mutated.loc[mutated.revision_id == "correction", "close"] = 999
    pd.testing.assert_frame_equal(early, as_of(mutated, "2025-07-02T21:00:00Z"))
    late = as_of(frame, "2025-07-03T20:00:00Z")
    assert late.close.tolist() == [104, 103]


@pytest.mark.parametrize(
    "changes,match",
    [
        ({"event_time": "2025-07-02 20:00:00"}, "explicit timezone"),
        ({"available_at": "2025-07-02T19:59:00Z"}, "cannot precede"),
        ({"open": float("inf")}, "finite"),
        ({"close": 110}, "OHLC"),
        ({"volume": -1}, "nonnegative"),
        ({"instrument_id": "MISSING.XNYS"}, "unknown instrument"),
    ],
)
def test_invalid_bars_rejected(tmp_path, changes, match):
    folder = source(tmp_path, [bar(**changes)])
    with pytest.raises(ValueError, match=match):
        import_dataset(folder, tmp_path / "store")


@pytest.mark.parametrize(
    "revision,available",
    [
        ("original", "2025-07-03T20:00:00Z"),
        ("correction", "2025-07-02T20:00:00Z"),
    ],
)
def test_logical_duplicate_revision_rejected(tmp_path, revision, available):
    folder = source(
        tmp_path, [bar(revision_id="original"), bar(revision_id=revision, available_at=available)]
    )
    with pytest.raises(ValueError, match="duplicate logical revision"):
        import_dataset(folder, tmp_path / "store")


def test_us_canada_holiday_discrepancy(tmp_path):
    valid = [bar(event="2025-07-01T20:00:00Z"), bar("FICTCA.XTSE", "2025-07-04T20:00:00Z")]
    root = tmp_path / "store"
    imported = import_dataset(source(tmp_path, valid), root)
    assert imported.row_count == 2
    assert any("missing" in warning for warning in imported.limitations)
    invalid_ca = valid + [bar("FICTCA.XTSE", "2025-07-01T20:00:00Z")]
    with pytest.raises(ValueError, match="XTSE.*holiday/session close"):
        import_dataset(source(tmp_path, invalid_ca), root)
    with pytest.raises(ValueError, match="XNYS.*holiday/session close"):
        import_dataset(source(tmp_path, valid + [bar(event="2025-07-04T20:00:00Z")]), root)


def test_hourly_halfday_and_final_partial_bar(tmp_path):
    # Nov 28: US closes 13:00 Eastern, Canada closes 16:00 Eastern.
    records = [bar(event=f"2025-11-28T{time}:00Z") for time in ["15:30", "16:30", "17:30", "18:00"]]
    records += [
        bar("FICTCA.XTSE", f"2025-11-28T{time}:00Z")
        for time in ["15:30", "16:30", "17:30", "18:30", "19:30", "20:30", "21:00"]
    ]
    folder = source(tmp_path, records, interval="1h")
    manifest = import_dataset(folder, tmp_path / "store")
    assert manifest.row_count == 11
    assert not any("missing" in x for x in manifest.limitations)
    with pytest.raises(ValueError, match="not a valid 1h endpoint"):
        import_dataset(
            source(tmp_path, records + [bar(event="2025-11-28T18:30:00Z")], interval="1h"),
            tmp_path / "store",
        )


def test_actions_fx_and_publication_time(tmp_path):
    actions = [
        dict(
            instrument_id="FICTUS.XNYS",
            event_time="2025-07-02T13:30:00Z",
            available_at="2025-07-02T13:30:00Z",
            type="dividend",
            cash_amount=1.25,
            currency="USD",
            ratio=None,
        ),
        dict(
            instrument_id="FICTCA.XTSE",
            event_time="2025-07-02T13:30:00Z",
            available_at="2025-07-02T13:30:00Z",
            type="split",
            cash_amount=None,
            currency="CAD",
            ratio=2,
        ),
    ]
    fx = [
        dict(
            event_time="2025-07-01T16:00:00Z",
            available_at="2025-07-01T20:30:00Z",
            usd_cad=1.35,
            source="fiction",
        ),
        dict(
            event_time="2025-07-02T16:00:00Z",
            available_at="2025-07-02T20:30:00Z",
            usd_cad=1.40,
            source="fiction",
        ),
    ]
    root = tmp_path / "store"
    manifest = import_dataset(source(tmp_path, actions=actions, fx=fx), root)
    data = load_dataset(root, manifest.dataset_id)
    assert data.actions.type.tolist() == ["split", "dividend"]
    assert fx_as_of(data.fx, "2025-07-02T20:00:00Z").usd_cad == 1.35
    assert fx_as_of(data.fx, "2025-07-02T20:30:00Z").usd_cad == 1.40
    assert fx_as_of(data.fx, "2025-07-01T15:00:00Z") is None
    actions[0]["currency"] = "CAD"
    with pytest.raises(ValueError, match="currency must match"):
        import_dataset(source(tmp_path, actions=actions), root)


def test_limitations_and_integrity_and_safe_ids(tmp_path):
    root = tmp_path / "store"
    manifest = import_dataset(
        source(tmp_path, availability_basis="inferred", corporate_actions_status="unknown"), root
    )
    assert any("not point-in-time certified" in x for x in manifest.limitations)
    assert any("coverage unknown" in x for x in manifest.limitations)
    with pytest.raises(ValueError, match="SHA-256"):
        load_dataset(root, "../secret")
    (root / manifest.dataset_id / "bars.parquet").write_bytes(b"changed")
    with pytest.raises(ValueError, match="integrity error"):
        load_dataset(root, manifest.dataset_id)


def test_strict_configs_and_currency_funding():
    valid = dict(INSTRUMENTS[1])
    valid["currency"] = "USD"  # TSX also has USD-denominated listings.
    assert Instrument(**valid).currency == "USD"
    with pytest.raises(ValidationError):
        Instrument(**{**valid, "currency": "EUR"})
    with pytest.raises(ValidationError):
        StrategyConfig(unrecognized=1)
    with pytest.raises(ValidationError):
        StrategyConfig(lookback=2.5)
    with pytest.raises(ValidationError):
        StrategyConfig(max_weight=0.21)
    one_currency = RunConfig(dataset_id="a" * 64, initial_cash_usd=100, initial_cash_cad=0)
    assert one_currency.initial_cash_cad == 0
    with pytest.raises(ValidationError, match="positive initial funding"):
        RunConfig(dataset_id="a" * 64, initial_cash_usd=0, initial_cash_cad=0)


def test_offline_fixture_is_deterministic_and_has_both_markets(tmp_path):
    # Load script directly: examples is intentionally not an installed package.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "fixture", Path(__file__).parents[1] / "examples" / "generate_fixture.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    first = module.generate_fixture(tmp_path / "first")
    second = module.generate_fixture(tmp_path / "second")
    for path in first.iterdir():
        assert path.read_bytes() == (second / path.name).read_bytes()
    manifest = import_dataset(first, tmp_path / "store")
    data = load_dataset(tmp_path / "store", manifest.dataset_id)
    assert manifest.mode == "synthetic_fixture"
    assert (data.bars.groupby("instrument_id").size() >= 100).all()
    assert data.bars.groupby("instrument_id").close.std().min() > 1
    local_publication = data.fx.available_at.dt.tz_convert("America/Toronto")
    assert set(zip(local_publication.dt.hour, local_publication.dt.minute)) == {(16, 30)}


@pytest.mark.parametrize(
    "field,value",
    [
        ("mode", "historical"),
        ("corporate_actions_status", "unknown"),
        ("row_count", 123),
        ("limitations", ["mutated evidence label"]),
    ],
)
def test_manifest_provenance_cannot_change_under_same_identity(tmp_path, field, value):
    root = tmp_path / "store"
    manifest = import_dataset(source(tmp_path), root)
    path = root / manifest.dataset_id / "manifest.json"
    changed = json.loads(path.read_text())
    changed[field] = value
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="manifest metadata differs"):
        load_dataset(root, manifest.dataset_id)
    with pytest.raises(ValueError, match="manifest metadata differs"):
        list_datasets(root)


def test_source_changes_cannot_keep_identity_even_with_updated_digest(tmp_path):
    import hashlib

    root = tmp_path / "store"
    manifest = import_dataset(source(tmp_path), root)
    stored = root / manifest.dataset_id
    metadata_path = stored / "source" / "dataset.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["mode"] = "historical"
    metadata_path.write_text(json.dumps(metadata))
    manifest_path = stored / "manifest.json"
    document = json.loads(manifest_path.read_text())
    document["mode"] = "historical"
    document["source_files"]["dataset.json"] = hashlib.sha256(
        metadata_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="source content does not match dataset_id"):
        load_dataset(root, manifest.dataset_id)
