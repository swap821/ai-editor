from __future__ import annotations

import importlib
import inspect
import hashlib
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
            applied_at TEXT NOT NULL,
            digest TEXT NOT NULL DEFAULT ''
        )
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(schema_migrations)")}
    if "digest" not in columns:
        conn.execute(
            "ALTER TABLE schema_migrations ADD COLUMN digest TEXT NOT NULL DEFAULT ''"
        )


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    ensure_migrations_table(conn)
    cur = conn.execute("SELECT version FROM schema_migrations")
    return {row[0] for row in cur.fetchall()}


def apply_migrations(
    conn: sqlite3.Connection, *, scope: str | None = None
) -> list[tuple[int, str]]:
    """Apply pending migrations in version order and record their digests.

    ``scope`` keeps the mission and memory databases from applying each
    other's migrations.  Omitting it preserves the original compatibility
    behavior for callers that intentionally share one database.
    """
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
        migration_scope = getattr(migration, "scope", None)
        if scope is not None and migration_scope != scope:
            continue
        if migration.version in applied:
            continue
        migration.apply(conn)
        digest = hashlib.sha256(
            inspect.getsource(migration.__class__).encode("utf-8")
        ).hexdigest()
        conn.execute(
            "INSERT INTO schema_migrations "
            "(version, name, applied_at, digest) VALUES (?, ?, ?, ?)",
            (
                migration.version,
                migration.name,
                datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                digest,
            ),
        )
        run.append((migration.version, migration.name))
    return run


__all__ = ["Migration", "apply_migrations", "applied_versions"]
