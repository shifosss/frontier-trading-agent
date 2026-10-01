"""Inventory retained project evidence and select an explicit, reviewed Git publication set.

Read-only with respect to source/research/broker state; writes only docs/handover manifests.
Do not run research workers, load models, or acquire data from this utility.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "handover"
EXCLUDED_DIRS = {".git", ".venv", "node_modules", "__pycache__", "nautilus", "ponytail"}
RAW_DIRS = {"resources", "raw", "cache", "profiles", "captures", "pages"}
PRIVATE_DIRS = {"operations", "operator-ui-actual", "operator-ui-smoke", "operator-activation"}
SOURCE_SUFFIXES = {".py", ".md", ".ps1", ".toml"}
EVIDENCE_SUFFIXES = {".json", ".csv", ".jsonl", ".txt"}
PRIVATE_KEYS = re.compile(
    r'"(?:account_number|APCA-API-KEY-ID|APCA-API-SECRET-KEY|Authorization)"\s*:', re.I
)
RAW_NAMES = re.compile(
    r"(?:\.raw\.|frozen-yahoo|cost-.*page|snapshot|stdout|stderr|\.log$|\.body$)", re.I
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def publication_class(path: Path, size: int) -> str:
    relative = path.relative_to(ROOT)
    parts = set(relative.parts)
    if relative.parts[0] in {"data", "artifacts"}:
        return "local-only dataset, source, model, runtime or journal"
    if path.suffix in SOURCE_SUFFIXES:
        return "publish authored source or documentation unchanged"
    if parts & PRIVATE_DIRS or relative.name.startswith("operator_"):
        return "local-only operational/private evidence"
    if path.suffix not in EVIDENCE_SUFFIXES:
        return "local-only binary, media, model or runtime artifact"
    if parts & RAW_DIRS or RAW_NAMES.search(path.name):
        return "local-only original/vendor payload or operational snapshot"
    if size > 512 * 1024:
        return "local-only large evidence; recover from retained archive"
    body = path.read_text(encoding="utf-8", errors="replace")
    if PRIVATE_KEYS.search(body):
        return "local-only possible broker/authentication payload; review required"
    if path.suffix == ".json":
        try:
            value = json.loads(body)
        except json.JSONDecodeError:
            return "local-only unparsable evidence; original retained"
        if isinstance(value, dict) and (
            {"quotes", "bars", "trades", "filings", "companyfacts"} & value.keys()
        ):
            return "local-only row-level or original source payload"
    return "publish compact declaration, result, table or verification unchanged"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    errors = []
    paths = []
    for directory in (ROOT / ".qualification", ROOT / "data", ROOT / "artifacts"):
        if not directory.exists():
            continue

        def error(err: OSError) -> None:
            errors.append(
                {"path": str(err.filename), "error": type(err).__name__, "message": str(err)}
            )

        for folder, subdirs, filenames in os.walk(directory, onerror=error):
            subdirs[:] = [
                name
                for name in subdirs
                if name not in EXCLUDED_DIRS and name != "handover-20261001"
            ]
            for filename in filenames:
                path = Path(folder) / filename
                # The running broker journal/locks are private and mutable. Do not snapshot them.
                if path.parent == ROOT / "data" and filename.startswith("operator."):
                    continue
                if "operator" in path.relative_to(ROOT).parts and directory.name == "artifacts":
                    continue
                paths.append(path)

    def inspect(path: Path) -> dict:
        relative = path.relative_to(ROOT).as_posix()
        try:
            before = path.stat()
            decision = publication_class(path, before.st_size)
            identity = sha256(path)
            after = path.stat()
            stable = before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns
            return {
                "path": relative,
                "bytes": before.st_size,
                "sha256": identity,
                "mtime_utc": datetime.fromtimestamp(before.st_mtime, timezone.utc).isoformat(),
                "stable_during_inventory": stable,
                "publication": decision if stable else "local-only changed during inventory",
                "error": "",
            }
        except OSError as err:
            return {
                "path": relative,
                "bytes": "",
                "sha256": "",
                "mtime_utc": "",
                "stable_during_inventory": False,
                "publication": "unreadable; completeness gap retained",
                "error": type(err).__name__ + ": " + str(err),
            }

    with ThreadPoolExecutor(max_workers=4) as executor:
        rows = sorted(executor.map(inspect, paths), key=lambda row: row["path"])
    fields = [
        "path",
        "bytes",
        "sha256",
        "mtime_utc",
        "stable_during_inventory",
        "publication",
        "error",
    ]
    with (OUT / "artifact-inventory.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    selected = [row for row in rows if row["publication"].startswith("publish ")]
    (OUT / "publication-paths.txt").write_text(
        "".join(row["path"] + "\n" for row in selected), encoding="utf-8"
    )
    stamp = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema_version": 1,
        "snapshot_utc": stamp,
        "workspace": str(ROOT),
        "source_read_only": True,
        "research_executed": False,
        "records": len(rows),
        "inventoried_bytes": sum(row["bytes"] for row in rows if isinstance(row["bytes"], int)),
        "publication_files": len(selected),
        "publication_bytes": sum(row["bytes"] for row in selected),
        "decisions": dict(Counter(row["publication"] for row in rows)),
        "traversal_errors": errors,
        "file_errors": [row for row in rows if row["error"]],
        "excluded_directory_names": sorted(EXCLUDED_DIRS),
        "private_mutable_journal_excluded": True,
        "limits": [
            "Inventory excludes runtimes, plugins, dependencies and the live paper journal.",
            "Hashes identify bytes; they do not establish redistribution rights or qualification.",
            "Publication set must pass a separate privacy/history/Markdown review before staging.",
        ],
    }
    (OUT / "inventory-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: summary[key]
                for key in (
                    "snapshot_utc",
                    "records",
                    "inventoried_bytes",
                    "publication_files",
                    "publication_bytes",
                    "traversal_errors",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
