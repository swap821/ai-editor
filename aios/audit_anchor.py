"""External audit anchoring — API wrapper over the audit chain's get_anchor/verify_chain."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from aios.security.audit_logger import get_anchor, verify_chain

try:
    from aios import config

    _DEFAULT_DB = getattr(config, "AUDIT_DB_PATH", None)
except ImportError:
    _DEFAULT_DB = None

try:
    from aios import config as _config_mod

    _DEFAULT_DATA_DIR = getattr(_config_mod, "DATA_DIR", None)
except ImportError:
    _DEFAULT_DATA_DIR = None


def _resolve_db_path(db_path: Path | None) -> Path:
    resolved = db_path if db_path is not None else _DEFAULT_DB
    if resolved is None:
        raise RuntimeError("No audit db_path provided and no default configured.")
    return resolved


def _history_path() -> Path:
    if _DEFAULT_DATA_DIR is None:
        raise RuntimeError("No data directory configured for anchor history.")
    return Path(_DEFAULT_DATA_DIR) / "anchor_history.jsonl"


def _count_entries(db_path: Path) -> int:
    if not Path(db_path).exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT COUNT(*) FROM tamper_audit_trail").fetchone()
        return int(row[0]) if row else 0
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def get_external_anchor(db_path: Path | None = None) -> dict[str, Any]:
    resolved = _resolve_db_path(db_path)
    anchor = dict(get_anchor(resolved))
    anchor["verified_at"] = datetime.now(timezone.utc).isoformat()
    anchor["chain_length"] = _count_entries(resolved)
    return anchor


def verify_anchor(expected_hash: str, db_path: Path | None = None) -> dict[str, Any]:
    resolved = _resolve_db_path(db_path)
    anchor = get_anchor(resolved)
    current_hash = anchor.get("head_hash")
    chain_status = verify_chain(db_path=resolved)
    return {
        "matches": current_hash == expected_hash,
        "chain_valid": bool(chain_status.valid),
        "current_hash": current_hash,
        "expected_hash": expected_hash,
        "anchor": anchor,
    }


def publish_anchor(
    publisher: Callable[[dict[str, Any]], None], db_path: Path | None = None
) -> dict[str, Any]:
    anchor = get_external_anchor(db_path)
    try:
        publisher(anchor)
    except Exception as exc:  # noqa: BLE001
        result = dict(anchor)
        result["published"] = False
        result["error"] = str(exc)
        return result

    result = dict(anchor)
    result["published"] = True

    try:
        history_file = _history_path()
        history_file.parent.mkdir(parents=True, exist_ok=True)
        with history_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(result, sort_keys=True) + "\n")
    except Exception:  # noqa: BLE001
        pass

    return result


def anchor_history(
    db_path: Path | None = None, limit: int = 10
) -> list[dict[str, Any]]:
    history_file = _history_path()
    if not history_file.exists():
        return []

    entries: list[dict[str, Any]] = []
    with history_file.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if limit <= 0:
        return entries
    return entries[-limit:]


__all__ = [
    "get_external_anchor",
    "verify_anchor",
    "publish_anchor",
    "anchor_history",
]
