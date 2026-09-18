"""Read the saved research workflow without consuming model or data access."""

import json
from pathlib import Path

_PATTERNS = {
    "model-campaigns": "model-campaigns/*/campaign.json",
    "campaigns": "*/campaign.json",
    "frozen": "frozen/*.json",
    "observations": "observations/*.json",
}


def list_artifacts(artifact_root: Path, kind: str) -> list[dict]:
    if kind not in _PATTERNS:
        raise ValueError(f"Unknown artifact collection: {kind}")
    root = Path(artifact_root).resolve()
    records = []
    for path in root.glob(_PATTERNS[kind]):
        if not path.resolve().is_relative_to(root):
            raise ValueError("Saved workflow artifact is outside artifact root")
        records.append(json.loads(path.read_text(encoding="utf-8")))
    return sorted(
        records, key=lambda row: row.get("created_at", row.get("as_of", "")), reverse=True
    )
