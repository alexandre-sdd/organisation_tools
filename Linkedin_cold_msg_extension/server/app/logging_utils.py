import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def append_ndjson(path: Path, record: dict[str, Any]) -> None:
    """Append one JSON object as a single line.

    Never raises: logging must not break the request path.
    """

    try:
        ensure_dir(path.parent)
        line = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
            f.write("\n")
    except Exception:
        return
