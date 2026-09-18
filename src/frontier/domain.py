"""Public data and run contracts. All prices are raw and native-currency."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Currency = Literal["USD", "CAD"]
Venue = Literal["XNAS", "XNYS", "ARCX", "XTSE"]
CALENDAR_BY_VENUE = {"XNAS": "XNYS", "XNYS": "XNYS", "ARCX": "XNYS", "XTSE": "XTSE"}


def utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include an explicit timezone")
    return value.astimezone(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Instrument(StrictModel):
    id: str
    symbol: str = Field(min_length=1)
    venue: Venue
    currency: Currency
    asset_type: Literal["stock", "etf"]
    exposure_group: str = Field(min_length=1)

    @model_validator(mode="after")
    def consistent_identity(self):
        if self.id != f"{self.symbol}.{self.venue}":
            raise ValueError("instrument id must equal SYMBOL.VENUE")

        return self


class DatasetMetadata(StrictModel):
    """dataset.json fields, excluding identities derived during import."""

    schema_version: Literal[1] = 1
    name: str = Field(min_length=1)
    mode: Literal["synthetic_fixture", "historical"]
    source: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    retrieved_at: datetime
    usage_notes: str = Field(min_length=1)
    availability_basis: Literal["observed", "documented", "inferred", "unknown"]
    adjustment_policy: Literal["raw"] = "raw"
    corporate_actions_status: Literal["complete", "unknown"]
    instruments: list[Instrument] = Field(min_length=1)
    interval: Literal["1d", "1h"]
    limitations: list[str] = Field(default_factory=list)

    _utc_retrieved = field_validator("retrieved_at")(utc_datetime)

    @field_validator("instruments")
    @classmethod
    def unique_instruments(cls, instruments):
        if len({i.id for i in instruments}) != len(instruments):
            raise ValueError("instrument IDs must be unique")
        return instruments


class DatasetManifest(DatasetMetadata):
    dataset_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    start: datetime
    end: datetime
    row_count: int = Field(gt=0)
    files: dict[str, str]
    source_files: dict[str, str]
    ingested_at: datetime

    _utc_times = field_validator("start", "end", "ingested_at")(utc_datetime)


class StrategyConfig(StrictModel):
    family: Literal["cash", "passive", "trend", "reversion"] = "passive"
    lookback: int = Field(default=20, ge=2, strict=True)
    rebalance_every: int = Field(default=5, ge=1, strict=True)
    max_weight: float = Field(default=0.2, gt=0, le=0.2)
    name: str = Field(default="passive", min_length=1)
    long_only: Literal[True] = True
    whole_shares: Literal[True] = True
    currency_funding: Literal["separate"] = "separate"


class RunConfig(StrictModel):
    dataset_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    initial_cash_usd: float = Field(default=10_000, ge=0)
    initial_cash_cad: float = Field(default=10_000, ge=0)
    base_currency: Currency = "CAD"
    commission_per_order: float = Field(default=1, ge=0)
    slippage_bps: float = Field(default=5, ge=0)
    seed: int = Field(default=1729, strict=True)
    allow_incomplete_actions: bool = False
    decision_timing: Literal["available_close"] = "available_close"
    fill_timing: Literal["next_eligible_open"] = "next_eligible_open"

    @model_validator(mode="after")
    def funded_account(self):
        if self.initial_cash_usd + self.initial_cash_cad <= 0:
            raise ValueError("at least one currency must have positive initial funding")
        return self


@dataclass
class MarketDataset:
    manifest: DatasetManifest
    bars: pd.DataFrame
    actions: pd.DataFrame
    fx: pd.DataFrame
