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
    4: (),
    5: (),
}


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _validate_compact_table(
    connection: sqlite3.Connection,
    *,
    table: str,
    columns: tuple[tuple[str, str, int, int], ...],
    json_column: str,
    secondary_index: tuple[str, str] | None,
) -> None:
    info = connection.execute(
        f"PRAGMA table_info({_identifier(table)})"
    ).fetchall()
    observed = tuple(
        (row[1], row[2].upper(), row[3], row[5])
        for row in info
        if len(row) >= 6
    )
    if observed != columns:
        raise ValueError(f"database has invalid schema v4 table {table}")
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    sql = row[0] if row is not None and len(row) == 1 else None
    if not isinstance(sql, str):
        raise ValueError(f"database has invalid schema v4 table {table}")
    normalized = " ".join(sql.upper().split())
    if (
        "WITHOUT ROWID" not in normalized
        or f"JSON_VALID({json_column.upper()})" not in normalized
        or f"JSON_TYPE({json_column.upper()}) = 'OBJECT'" not in normalized
    ):
        raise ValueError(f"database has invalid schema v4 table {table}")
    indexes = connection.execute(
        f"PRAGMA index_list({_identifier(table)})"
    ).fetchall()
    secondary = tuple(
        (index[1], index[2], index[3], index[4])
        for index in indexes
        if len(index) >= 5 and index[3] != "pk"
    )
    expected_secondary = (
        ((secondary_index[0], 0, "c", 0),)
        if secondary_index is not None
        else ()
    )
    if secondary != expected_secondary:
        raise ValueError(
            f"database has invalid schema v4+ indexes on {table}"
        )
    if secondary_index is not None:
        index_columns = connection.execute(
            f"PRAGMA index_info({_identifier(secondary_index[0])})"
        ).fetchall()
        if tuple(row[2] for row in index_columns) != (secondary_index[1],):
            raise ValueError(
                f"database has invalid schema v4+ index on {table}"
            )


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
    version_info = connection.execute(
        "PRAGMA table_info(_schema_version)"
    ).fetchall()
    if tuple(
        (row[1], row[2].upper(), row[3], row[5])
        for row in version_info
        if len(row) >= 6
    ) != (("version", "INTEGER", 1, 0),):
        raise ValueError("database has invalid NuSelf schema metadata")
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
    if version in (4, 5):
        expected_tables = {
            "_schema_version",
            "records",
            "workspace_entries",
        }
        if tables != expected_tables:
            raise ValueError("database has invalid schema v4+ table set")
        _validate_compact_table(
            connection,
            table="records",
            columns=(
                ("collection", "TEXT", 1, 1),
                ("id", "TEXT", 1, 2),
                ("payload", "TEXT", 1, 0),
            ),
            json_column="payload",
            secondary_index=(
                ("idx_records_collection", "collection")
                if version == 4
                else None
            ),
        )
        _validate_compact_table(
            connection,
            table="workspace_entries",
            columns=(
                ("namespace", "TEXT", 1, 1),
                ("key", "TEXT", 1, 2),
                ("value", "TEXT", 1, 0),
                ("created_at", "TEXT", 1, 0),
                ("updated_at", "TEXT", 1, 0),
            ),
            json_column="value",
            secondary_index=(
                ("idx_workspace_entries_ns", "namespace")
                if version == 4
                else None
            ),
        )
        return version
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
