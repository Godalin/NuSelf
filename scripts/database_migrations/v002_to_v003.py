"""Historical v2→v3 migration: add the current collection set."""

from __future__ import annotations

import sqlite3

from nuself.storage import COLLECTION_NAMES


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def upgrade(connection: sqlite3.Connection) -> None:
    for name in COLLECTION_NAMES:
        connection.execute(
            f"CREATE TABLE IF NOT EXISTS "
            f"{_identifier(f'col_{name}')} (id TEXT PRIMARY KEY)"
        )
