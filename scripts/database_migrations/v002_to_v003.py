"""Historical v2→v3 migration: add the frozen v3 collection set."""

from __future__ import annotations

import sqlite3

from scripts.database_migrations.schema_identity import SCHEMA_COLLECTIONS


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def upgrade(connection: sqlite3.Connection) -> None:
    for name in SCHEMA_COLLECTIONS[3]:
        connection.execute(
            f"CREATE TABLE IF NOT EXISTS "
            f"{_identifier(f'col_{name}')} (id TEXT PRIMARY KEY)"
        )
