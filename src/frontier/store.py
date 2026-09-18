"""Single-coordinator durable run and global evaluation-access registry."""

import json
import platform
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import pandas as pd

from frontier.domain import RunConfig


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def _boundary(value):
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError("evaluation boundary must be a valid date or timestamp")
    # Date-only campaign boundaries are defined as UTC midnight.
    if timestamp.tzinfo is None:
        if isinstance(value, str) and len(value) == 10:
            timestamp = timestamp.tz_localize("UTC")
        else:
            raise ValueError("evaluation timestamp requires timezone or YYYY-MM-DD date")
    return timestamp.tz_convert("UTC").isoformat()


class Registry:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK(status IN ('RUNNING','COMPLETED','FAILED')),
                    mode TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    config TEXT NOT NULL,
                    code_identity TEXT NOT NULL,
                    runtime_identity TEXT NOT NULL,
                    summary TEXT,
                    artifact_path TEXT,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS evaluation_access (
                    id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL,
                    start TEXT NOT NULL,
                    end TEXT NOT NULL,
                    campaign_id TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS access_dataset_time
                    ON evaluation_access(dataset_id,start,end);
            """)

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _record(row):
        result = dict(row)
        for key in ("config", "runtime_identity", "summary"):
            if key in result and result[key] is not None:
                result[key] = json.loads(result[key])
        return result

    def start_run(self, config: RunConfig, mode: str, code_identity: str) -> str:
        if mode not in {"synthetic_fixture", "historical"}:
            raise ValueError("run mode must be inherited from synthetic_fixture/historical dataset")
        if not code_identity.strip():
            raise ValueError("code_identity must be nonempty")
        run_id = uuid.uuid4().hex
        runtime = {
            "python": sys.version,
            "platform": platform.platform(),
            "frontier": version("frontier-trading"),
            "nautilus_trader": version("nautilus-trader"),
        }
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO runs(id,status,mode,created_at,config,code_identity,runtime_identity) "
                "VALUES (?,'RUNNING',?,?,?,?,?)",
                (run_id, mode, _now(), config.model_dump_json(), code_identity, _json(runtime)),
            )
        return run_id

    def finish_run(self, run_id, summary: dict, artifact_path: str):
        summary_json = _json(summary)
        with self._connect() as connection:
            changed = connection.execute(
                "UPDATE runs SET status='COMPLETED',completed_at=?,summary=?,artifact_path=? "
                "WHERE id=? AND status='RUNNING'",
                (_now(), summary_json, artifact_path, run_id),
            ).rowcount
            if changed != 1:
                raise ValueError("run does not exist or is already terminal; results are immutable")

    def fail_run(self, run_id, error: str):
        with self._connect() as connection:
            changed = connection.execute(
                "UPDATE runs SET status='FAILED',completed_at=?,error=? "
                "WHERE id=? AND status='RUNNING'",
                (_now(), error, run_id),
            ).rowcount
            if changed != 1:
                raise ValueError("run does not exist or is already terminal; results are immutable")

    def list_runs(self) -> list[dict]:
        with self._connect() as connection:
            return [
                self._record(row)
                for row in connection.execute("SELECT * FROM runs ORDER BY created_at DESC,id")
            ]

    def get_run(self, id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id=?", (id,)).fetchone()
        if row is None:
            raise KeyError(f"run not found: {id}")
        return self._record(row)

    def record_evaluation_access(self, dataset_id, start, end, campaign_id, purpose) -> list[dict]:
        """Record access and return prior globally overlapping accesses.

        Intervals are closed: touching boundaries count as overlap. Campaign names
        do not reset exposure. Dataset identities are the overlap scope.
        """
        start, end = _boundary(start), _boundary(end)
        if start > end:
            raise ValueError("evaluation start must be <= end")
        if not dataset_id or not campaign_id or not purpose:
            raise ValueError("dataset_id, campaign_id and purpose must be nonempty")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            overlaps = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM evaluation_access WHERE dataset_id=? AND start<=? AND end>=? "
                    "ORDER BY created_at,id",
                    (dataset_id, end, start),
                )
            ]
            connection.execute(
                "INSERT INTO evaluation_access VALUES (?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, dataset_id, start, end, campaign_id, purpose, _now()),
            )
        return overlaps
