"""Schema v4↔v5: remove redundant compact-table prefix indexes."""

from __future__ import annotations

import sqlite3


def upgrade(connection: sqlite3.Connection) -> None:
    connection.execute("DROP INDEX idx_records_collection")
    connection.execute("DROP INDEX idx_workspace_entries_ns")


def downgrade(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE INDEX idx_records_collection ON records(collection)"
    )
    connection.execute(
        "CREATE INDEX idx_workspace_entries_ns "
        "ON workspace_entries(namespace)"
    )
