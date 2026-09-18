"""Small durable paper journal; no second portfolio accounting engine."""

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def encode(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


@contextmanager
def operator_lock(workspace):
    """Hold an OS lock across individual durable commits and broker requests."""
    path = Path(workspace) / "data/operator.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0)
        stream.write(b"0")
        stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            def acquire():
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)

            def release():
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            def acquire():
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)

            def release():
                fcntl.flock(stream, fcntl.LOCK_UN)

        try:
            acquire()
        except OSError as exc:
            raise RuntimeError("Another paper operator cycle is running") from exc
        try:
            yield
        finally:
            stream.seek(0)
            release()


class OperatorStore:
    def __init__(self, workspace):
        self.path = Path(workspace) / "data/operator.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS cycles (
                    session TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                    plan TEXT NOT NULL, capture TEXT NOT NULL, status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS intents (
                    id TEXT PRIMARY KEY, session TEXT NOT NULL, payload TEXT NOT NULL,
                    eligible_at TEXT NOT NULL, expires_at TEXT NOT NULL,
                    state TEXT NOT NULL, broker TEXT, error TEXT
                );
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY, observed_at TEXT NOT NULL,
                    snapshot TEXT NOT NULL, risk TEXT
                );
                CREATE TABLE IF NOT EXISTS flows (
                    id TEXT PRIMARY KEY, observed_at TEXT NOT NULL,
                    amount_usd REAL NOT NULL, evidence TEXT NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=2)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def get(self, key, default=None):
        with self.connect() as connection:
            row = connection.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        with self.connect() as connection:
            connection.execute("INSERT OR REPLACE INTO state VALUES (?,?)", (key, encode(value)))

    def orders(self):
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM intents ORDER BY rowid").fetchall()
        return [self.decode(row, ("payload", "broker")) for row in rows]

    @staticmethod
    def decode(row, fields):
        record = dict(row)
        for key in fields:
            if record[key] is not None:
                record[key] = json.loads(record[key])
        return record

    def flows(self):
        with self.connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM flows ORDER BY rowid")]

    def update_order(self, identity, state, broker=None, error=None):
        with self.connect() as connection:
            connection.execute(
                "UPDATE intents SET state=?,broker=?,error=? WHERE id=?",
                (state, encode(broker) if broker is not None else None, error, identity),
            )

    def latest_cycle(self):
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM cycles ORDER BY rowid DESC LIMIT 1").fetchone()
        return self.decode(row, ("plan", "capture")) if row else None

    def save_plan(self, session, created_at, plan, capture, intents):
        with self.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM cycles WHERE session=?", (session,)
            ).fetchone()
            if exists:
                return False
            connection.execute(
                "INSERT INTO cycles VALUES (?,?,?,?,?)",
                (session, created_at, encode(plan), encode(capture), "PLANNED"),
            )
            if "next_position_state" in plan:
                connection.execute(
                    "INSERT OR REPLACE INTO state VALUES ('position_state',?)",
                    (encode(plan["next_position_state"]),),
                )
            for intent in intents:
                connection.execute(
                    "INSERT INTO intents VALUES (?,?,?,?,?,'PLANNED',NULL,NULL)",
                    (
                        intent["id"],
                        session,
                        encode(intent["payload"]),
                        plan["eligible_at"],
                        plan["expires_at"],
                    ),
                )
        return True

    def observe(self, timestamp, snapshot, risk=None):
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO observations(observed_at,snapshot,risk) VALUES (?,?,?)",
                (timestamp, encode(snapshot), encode(risk) if risk else None),
            )
            connection.execute(
                "INSERT OR REPLACE INTO state VALUES ('snapshot',?)", (encode(snapshot),)
            )
            if risk:
                connection.execute(
                    "INSERT OR REPLACE INTO state VALUES ('risk',?)", (encode(risk),)
                )
