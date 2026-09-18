"""Immutable, calendar-checked Parquet imports and point-in-time reads."""

import hashlib
import io
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import exchange_calendars as xcals
import numpy as np
import pandas as pd

from frontier.domain import CALENDAR_BY_VENUE, DatasetManifest, DatasetMetadata, MarketDataset

BARS_COLUMNS = [
    "instrument_id",
    "event_time",
    "available_at",
    "open",
    "high",
    "low",
    "close",
    "volume",
]
ACTIONS_COLUMNS = [
    "instrument_id",
    "event_time",
    "available_at",
    "type",
    "cash_amount",
    "currency",
    "ratio",
]
FX_COLUMNS = ["event_time", "available_at", "usd_cad", "source"]


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _timestamp(value, label: str) -> pd.Timestamp:
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}: invalid timestamp {value!r}") from exc
    if pd.isna(result) or result.tzinfo is None:
        raise ValueError(f"{label}: timestamp must include an explicit timezone")
    return result.tz_convert("UTC")


def _read_frame(raw: bytes | None, columns: list[str], name: str) -> pd.DataFrame:
    if raw is None:
        return pd.DataFrame(columns=columns + ["revision_id", "ingested_at"])
    frame = pd.read_csv(io.BytesIO(raw), dtype={"revision_id": str})
    missing = set(columns) - set(frame.columns)
    unexpected = set(frame.columns) - set(columns) - {"revision_id"}
    if missing or unexpected:
        raise ValueError(f"{name}: missing columns {sorted(missing)}, unknown {sorted(unexpected)}")
    for column in ("event_time", "available_at"):
        frame[column] = pd.to_datetime(
            [_timestamp(v, f"{name} row {i + 2} {column}") for i, v in enumerate(frame[column])],
            utc=True,
        )
    if (frame.available_at < frame.event_time).any():
        raise ValueError(f"{name}: available_at cannot precede event_time")
    if "revision_id" not in frame:
        frame["revision_id"] = "original"
    if frame.revision_id.isna().any() or frame.revision_id.str.strip().eq("").any():
        raise ValueError(f"{name}: revision_id must be nonempty")
    keys = ["event_time"]
    if "instrument_id" in frame:
        keys.insert(0, "instrument_id")
    if name == "actions":
        keys.append("type")
    for revision_key in ("revision_id", "available_at"):
        if frame.duplicated(keys + [revision_key]).any():
            raise ValueError(f"{name}: duplicate logical revision ({revision_key})")
    return frame.sort_values(keys + ["available_at", "revision_id"]).reset_index(drop=True)


def _numeric(frame, columns, name, *, positive=True):
    for column in columns:
        try:
            frame[column] = pd.to_numeric(frame[column], errors="raise").astype(float)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name}: {column} must be numeric") from exc
        values = frame[column]
        invalid = ~np.isfinite(values) | (values <= 0 if positive else values < 0)
        if invalid.any():
            raise ValueError(
                f"{name}: {column} must be finite and {'positive' if positive else 'nonnegative'}"
            )


def _known_instruments(frame, metadata, name):
    unknown = set(frame.instrument_id) - {i.id for i in metadata.instruments}
    if unknown:
        raise ValueError(f"{name}: unknown instrument_id {sorted(map(str, unknown))}")


def session_endpoints(calendar, session, interval: str) -> pd.DatetimeIndex:
    """Exchange close or hourly endpoints, including a final partial hour."""
    close = calendar.session_close(session)
    if interval == "1d":
        return pd.DatetimeIndex([close])
    opening = calendar.session_open(session)
    points = list(pd.date_range(opening + pd.Timedelta(hours=1), close, freq="h"))
    if not points or points[-1] != close:
        points.append(close)
    return pd.DatetimeIndex(points)


def _validate_calendars(bars, metadata):
    warnings = []
    start_date = bars.event_time.min().date()
    end_date = bars.event_time.max().date()
    for instrument in metadata.instruments:
        calendar = xcals.get_calendar(
            CALENDAR_BY_VENUE[instrument.venue],
            start=str(start_date - pd.Timedelta(days=10)),
            end=str(end_date + pd.Timedelta(days=10)),
        )
        sessions = calendar.sessions_in_range(str(start_date), str(end_date))
        expected = {t for s in sessions for t in session_endpoints(calendar, s, metadata.interval)}
        actual = set(bars.loc[bars.instrument_id == instrument.id, "event_time"])
        invalid = actual - expected
        if invalid:
            raise ValueError(
                f"bars: {instrument.id} {min(invalid).isoformat()} is not a valid "
                f"{metadata.interval} endpoint on {calendar.name} (holiday/session close)"
            )
        missing = expected - actual
        if missing:
            warnings.append(
                f"{instrument.id}: {len(missing)} missing {metadata.interval} "
                "session endpoints; no fill-forward"
            )
    return warnings


def _validate_actions(actions, metadata):
    if actions.empty:
        return
    _known_instruments(actions, metadata, "actions")
    if not actions.type.isin(["dividend", "split"]).all():
        raise ValueError("actions: type must be dividend or split")
    currencies = {i.id: i.currency for i in metadata.instruments}
    for i, row in actions.iterrows():
        if row.currency != currencies[row.instrument_id]:
            raise ValueError(f"actions row {i + 2}: currency must match instrument currency")
        field = "cash_amount" if row.type == "dividend" else "ratio"
        try:
            value = float(row[field])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"actions row {i + 2}: {field} must be numeric") from exc
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f"actions row {i + 2}: {field} must be finite and positive")
        other = "ratio" if row.type == "dividend" else "cash_amount"
        if pd.notna(row[other]):
            raise ValueError(f"actions row {i + 2}: {other} must be blank for {row.type}")
    for field in ("cash_amount", "ratio"):
        actions[field] = pd.to_numeric(actions[field], errors="raise").astype(float)


def _validated_sources(raw):
    metadata = DatasetMetadata.model_validate_json(raw["dataset.json"])
    bars = _read_frame(raw["bars.csv"], BARS_COLUMNS, "bars")
    actions = _read_frame(raw.get("actions.csv"), ACTIONS_COLUMNS, "actions")
    fx = _read_frame(raw.get("fx.csv"), FX_COLUMNS, "fx")
    if bars.empty:
        raise ValueError("bars: at least one bar is required")
    _known_instruments(bars, metadata, "bars")
    _numeric(bars, ["open", "high", "low", "close"], "bars")
    _numeric(bars, ["volume"], "bars", positive=False)
    if (
        (bars.low > bars[["open", "close"]].min(axis=1))
        | (bars.high < bars[["open", "close"]].max(axis=1))
    ).any():
        raise ValueError("bars: OHLC bounds require low <= open/close <= high")
    limitations = list(metadata.limitations) + _validate_calendars(bars, metadata)
    if metadata.availability_basis in {"inferred", "unknown"}:
        limitations.append(
            f"Availability timestamps are {metadata.availability_basis}; "
            "not point-in-time certified"
        )
    if metadata.corporate_actions_status == "unknown":
        limitations.append("Corporate action coverage unknown; raw-price exploratory data")
    _validate_actions(actions, metadata)
    if not fx.empty:
        _numeric(fx, ["usd_cad"], "fx")
        if fx.source.isna().any() or fx.source.astype(str).str.strip().eq("").any():
            raise ValueError("fx: source must be nonempty")
    frames = {"bars": bars, "actions": actions, "fx": fx}
    return metadata, frames, list(dict.fromkeys(limitations))


def _content_id(metadata, frames, source_files):
    semantic = {
        "metadata": metadata.model_dump(mode="json"),
        "source_files": source_files,
        "frames": {
            name: json.loads(frame.to_json(orient="records", date_format="iso", date_unit="ns"))
            for name, frame in frames.items()
        },
    }
    return _digest(_json_bytes(semantic))


def import_dataset(source_dir: Path, data_root: Path) -> DatasetManifest:
    """Validate source CSVs, write immutable content-addressed dataset, return manifest.

    Identity includes canonical metadata/frames AND raw source digests: even a byte-only
    source revision remains distinguishable. Local ingestion time never affects identity.
    """
    source_dir, data_root = Path(source_dir), Path(data_root)
    raw = {"dataset.json": (source_dir / "dataset.json").read_bytes()}
    for name in ("bars.csv", "actions.csv", "fx.csv"):
        path = source_dir / name
        if name == "bars.csv" or path.exists():
            raw[name] = path.read_bytes()
    metadata, frames, limitations = _validated_sources(raw)
    bars = frames["bars"]
    source_files = {name: _digest(content) for name, content in raw.items()}
    dataset_id = _content_id(metadata, frames, source_files)
    data_root.mkdir(parents=True, exist_ok=True)
    destination = data_root / dataset_id
    if destination.exists():
        return load_dataset(data_root, dataset_id).manifest
    ingested_at = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory(prefix=".import-", dir=data_root) as temp:
        stage = Path(temp) / dataset_id
        stage.mkdir()
        files = {}
        for name, frame in frames.items():
            frame["ingested_at"] = pd.to_datetime([ingested_at] * len(frame), utc=True)
            filename = f"{name}.parquet"
            frame.to_parquet(stage / filename, engine="pyarrow", index=False)
            files[filename] = _digest((stage / filename).read_bytes())
        (stage / "source").mkdir()
        for name, content in raw.items():
            (stage / "source" / name).write_bytes(content)
        manifest = DatasetManifest(
            **metadata.model_dump(exclude={"limitations"}),
            dataset_id=dataset_id,
            start=bars.event_time.min().to_pydatetime(),
            end=bars.event_time.max().to_pydatetime(),
            row_count=len(bars),
            files=files,
            source_files=source_files,
            ingested_at=ingested_at,
            limitations=list(dict.fromkeys(limitations)),
        )
        (stage / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        try:
            stage.rename(destination)
        except FileExistsError:
            return load_dataset(data_root, dataset_id).manifest
    return manifest


def _dataset_path(data_root: Path, dataset_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", dataset_id):
        raise ValueError("dataset_id must be a 64-character lowercase SHA-256 digest")
    root = Path(data_root).resolve()
    path = (root / dataset_id).resolve()
    if path.parent != root:
        raise ValueError("dataset path must remain inside data_root")
    return path


def load_dataset(data_root: Path, dataset_id: str) -> MarketDataset:
    """Verify stored digests, then perform analytical reads through DuckDB."""
    path = _dataset_path(data_root, dataset_id)
    manifest = DatasetManifest.model_validate_json((path / "manifest.json").read_bytes())
    if manifest.dataset_id != dataset_id:
        raise ValueError("manifest dataset_id does not match directory")
    if set(manifest.files) != {"bars.parquet", "actions.parquet", "fx.parquet"}:
        raise ValueError("manifest must describe bars/actions/fx Parquet files")
    if (
        not {"dataset.json", "bars.csv"}
        <= set(manifest.source_files)
        <= {"dataset.json", "bars.csv", "actions.csv", "fx.csv"}
    ):
        raise ValueError("manifest contains invalid source paths")
    for base, mapping in ((path, manifest.files), (path / "source", manifest.source_files)):
        for filename, digest in mapping.items():
            if _digest((base / filename).read_bytes()) != digest:
                raise ValueError(f"dataset integrity error: {filename} digest differs")
    raw = {name: (path / "source" / name).read_bytes() for name in manifest.source_files}
    metadata, source_frames, limitations = _validated_sources(raw)
    if _content_id(metadata, source_frames, manifest.source_files) != dataset_id:
        raise ValueError("dataset integrity error: source content does not match dataset_id")
    expected_metadata = metadata.model_dump(exclude={"limitations"})
    actual_metadata = manifest.model_dump(include=set(expected_metadata))
    bars = source_frames["bars"]
    if (
        actual_metadata != expected_metadata
        or manifest.limitations != limitations
        or manifest.row_count != len(bars)
        or manifest.start != bars.event_time.min().to_pydatetime()
        or manifest.end != bars.event_time.max().to_pydatetime()
    ):
        raise ValueError("dataset integrity error: manifest metadata differs from source")
    frames = {}
    with duckdb.connect(":memory:") as connection:
        for name in ("bars", "actions", "fx"):
            frames[name] = connection.execute(
                "SELECT * FROM read_parquet(?)", [str(path / f"{name}.parquet")]
            ).fetchdf()
    return MarketDataset(manifest=manifest, **frames)


def list_datasets(data_root: Path) -> list[DatasetManifest]:
    root = Path(data_root)
    if not root.exists():
        return []
    return [
        load_dataset(root, path.name).manifest
        for path in sorted(root.iterdir())
        if path.is_dir() and re.fullmatch(r"[0-9a-f]{64}", path.name)
    ]


def as_of(bars: pd.DataFrame, decision_time) -> pd.DataFrame:
    """Latest knowable revision of each bar; input and future records stay untouched."""
    decision = _timestamp(decision_time, "decision_time")
    available = bars.loc[(bars.event_time <= decision) & (bars.available_at <= decision)]
    return (
        available.sort_values("available_at")
        .drop_duplicates(["instrument_id", "event_time"], keep="last")
        .sort_values(["event_time", "instrument_id"])
        .reset_index(drop=True)
    )


def fx_as_of(fx: pd.DataFrame, decision_time) -> pd.Series | None:
    """Most recent dated USD/CAD rate already published, never today's future fixing."""
    decision = _timestamp(decision_time, "decision_time")
    available = fx.loc[(fx.event_time <= decision) & (fx.available_at <= decision)]
    if available.empty:
        return None
    return available.sort_values(["event_time", "available_at"]).iloc[-1].copy()
