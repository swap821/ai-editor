from __future__ import annotations

import importlib
import inspect
import pkgutil
import sqlite3
from pathlib import Path
from typing import Protocol


class Migration(Protocol):
    """A versioned schema migration."""

    version: int
    name: str

    @staticmethod
    def apply(conn: sqlite3.Connection) -> None:
        ...


def ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    ensure_migrations_table(conn)
    cur = conn.execute("SELECT version FROM schema_migrations")
    return {row[0] for row in cur.fetchall()}


def apply_migrations(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    """Apply all pending migrations in version order."""
    from datetime import datetime, timezone

    ensure_migrations_table(conn)
    applied = applied_versions(conn)
    migrations: list[Migration] = []
    package_dir = Path(__file__).parent
    for _, module_name, _ in pkgutil.iter_modules([str(package_dir)]):
        if not module_name[0].isdigit():
            continue
        module = importlib.import_module(f"aios.infrastructure.storage.migrations.{module_name}")
        for _, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and hasattr(obj, "version") and hasattr(obj, "name"):
                migrations.append(obj())
    migrations.sort(key=lambda m: m.version)
    run: list[tuple[int, str]] = []
    for migration in migrations:
        if migration.version in applied:
            continue
        migration.apply(conn)
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (
                migration.version,
                migration.name,
                datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            ),
        )
        run.append((migration.version, migration.name))
    return run


__all__ = ["Migration", "apply_migrations", "applied_versions"]
