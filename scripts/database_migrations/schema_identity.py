"""Frozen collection identity for every schema supported by the script."""

from __future__ import annotations

import sqlite3

SCHEMA_COLLECTIONS: dict[int, tuple[str, ...]] = {
    1: (
        "memory_entries",
        "memory_candidates",
        "trace_nodes",
        "trace_edges",
        "reason_threads",
        "reason_steps",
        "persona_prompts",
        "profile_items",
        "source_documents",
        "source_chunks",
        "notification_outbox",
        "reflection_entries",
    ),
    2: (
        "memory_entries",
        "memory_candidates",
        "trace_nodes",
        "trace_edges",
        "reason_threads",
        "reason_steps",
        "persona_prompts",
        "profile_items",
        "source_documents",
        "source_chunks",
        "notification_outbox",
        "reflection_entries",
    ),
    3: (
        "memory_entries",
        "memory_candidates",
        "trace_nodes",
        "trace_edges",
        "reason_threads",
        "reason_steps",
        "persona_prompts",
        "profile_items",
        "source_documents",
        "source_chunks",
        "notification_outbox",
        "reflection_entries",
        "chat_threads",
        "memory_curator_cursors",
        "memory_curator_plans",
        "scheduler_state",
    ),
}


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def validate_schema(connection: sqlite3.Connection) -> int:
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        if len(row) == 1 and isinstance(row[0], str)
    }
    if "_schema_version" not in tables:
        raise ValueError("database is missing NuSelf schema metadata")
    rows = connection.execute(
        "SELECT version FROM _schema_version ORDER BY version"
    ).fetchall()
    versions = tuple(
        row[0]
        for row in rows
        if len(row) == 1 and type(row[0]) is int
    )
    if (
        len(versions) != len(rows)
        or not versions
        or versions != tuple(range(1, versions[-1] + 1))
    ):
        raise ValueError("database has invalid NuSelf schema version history")
    version = versions[-1]
    collections = SCHEMA_COLLECTIONS.get(version)
    if collections is None:
        raise ValueError(f"unsupported current version: {version}")
    for collection in collections:
        table = f"col_{collection}"
        if table not in tables:
            raise ValueError(f"database is missing collection table {table}")
        columns = connection.execute(
            f"PRAGMA table_info({_identifier(table)})"
        ).fetchall()
        if not any(
            len(column) >= 6
            and column[1] == "id"
            and column[5] == 1
            for column in columns
        ):
            raise ValueError(f"database collection {table} has no id primary key")
    return version
