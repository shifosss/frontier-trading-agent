"""Import the retained Longbridge SPY hourly snapshot, without network or login."""

import argparse
import json
from pathlib import Path

from frontier.sources import import_longbridge_snapshot

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--captured-at", default=None)
    args = parser.parse_args()
    result = import_longbridge_snapshot(args.workspace, captured_at=args.captured_at)
    print(
        json.dumps(
            {
                "manifest": result["manifest"],
                "evidence_path": result["evidence_path"],
                "comparison": {
                    key: value
                    for key, value in result["comparison"].items()
                    if key != "daily_comparison"
                },
            },
            indent=2,
        )
    )
