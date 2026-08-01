"""Schema v3↔v4: dynamic collection tables to one compact records table."""

from __future__ import annotations

import sqlite3
from typing import cast

from nuself.runtime.messages import decode_json_value, encode_json_value
from scripts.database_migrations.schema_identity import SCHEMA_COLLECTIONS

COLLECTIONS = SCHEMA_COLLECTIONS[3]


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _create_v4_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE records ("
        "collection TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL "
        "CHECK(json_valid(payload) AND json_type(payload) = 'object'), "
        "PRIMARY KEY (collection, id)) WITHOUT ROWID"
    )
    connection.execute(
        "CREATE INDEX idx_records_collection ON records(collection)"
    )
    existing_workspace = connection.execute(
        "SELECT 1 FROM sqlite_master "
        "WHERE type='table' AND name='workspace_entries'"
    ).fetchone()
    if existing_workspace is not None:
        connection.execute(
            "ALTER TABLE workspace_entries "
            "RENAME TO _workspace_entries_v3"
        )
    connection.execute(
        "CREATE TABLE workspace_entries ("
        "namespace TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL "
        "CHECK(json_valid(value) AND json_type(value) = 'object'), "
        "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
        "PRIMARY KEY (namespace, key)) WITHOUT ROWID"
    )
    if existing_workspace is not None:
        rows = connection.execute(
            "SELECT namespace, key, value, created_at, updated_at "
            "FROM _workspace_entries_v3"
        ).fetchall()
        for namespace, key, value, created_at, updated_at in rows:
            if (
                not isinstance(namespace, str)
                or not isinstance(key, str)
                or not isinstance(value, str)
                or not isinstance(created_at, str)
                or not isinstance(updated_at, str)
            ):
                raise ValueError("invalid schema v3 workspace row")
            decoded = decode_json_value(value)
            if not isinstance(decoded, dict):
                raise ValueError(
                    "schema v3 workspace value must be a JSON object"
                )
            connection.execute(
                "INSERT INTO workspace_entries VALUES (?, ?, ?, ?, ?)",
                (
                    namespace,
                    key,
                    encode_json_value(
                        cast(dict[str, object], decoded),
                        ensure_ascii=True,
                        separators=(",", ":"),
                    ),
                    created_at,
                    updated_at,
                ),
            )
        connection.execute("DROP TABLE _workspace_entries_v3")
    connection.execute(
        "CREATE INDEX idx_workspace_entries_ns "
        "ON workspace_entries(namespace)"
    )


def upgrade(connection: sqlite3.Connection) -> None:
    _create_v4_tables(connection)
    for collection in COLLECTIONS:
        table = f"col_{collection}"
        columns = tuple(
            row[1]
            for row in connection.execute(
                f"PRAGMA table_info({_identifier(table)})"
            ).fetchall()
        )
        rows = connection.execute(
            f"SELECT * FROM {_identifier(table)}"
        ).fetchall()
        for row in rows:
            record_id = row[columns.index("id")]
            if not isinstance(record_id, str) or not record_id:
                raise ValueError(f"invalid record ID in {table}")
            payload: dict[str, object] = {}
            for index, column in enumerate(columns):
                value = row[index]
                if column == "id" or value is None:
                    continue
                if not isinstance(value, str):
                    raise ValueError(f"non-JSON column in {table}")
                payload[column] = decode_json_value(value)
            connection.execute(
                "INSERT INTO records(collection, id, payload) VALUES (?, ?, ?)",
                (
                    collection,
                    record_id,
                    encode_json_value(
                        payload,
                        ensure_ascii=True,
                        separators=(",", ":"),
                    ),
                ),
            )
        connection.execute(f"DROP TABLE {_identifier(table)}")


def downgrade(connection: sqlite3.Connection) -> None:
    workspace_count = connection.execute(
        "SELECT COUNT(*) FROM workspace_entries"
    ).fetchone()
    if workspace_count != (0,):
        raise ValueError(
            "schema v4 workspace_entries must be exported before downgrade"
        )
    for collection in COLLECTIONS:
        table = f"col_{collection}"
        connection.execute(
            f"CREATE TABLE {_identifier(table)} (id TEXT PRIMARY KEY)"
        )
        rows = connection.execute(
            "SELECT id, payload FROM records WHERE collection = ?",
            (collection,),
        ).fetchall()
        decoded: list[tuple[str, dict[str, object]]] = []
        keys: set[str] = set()
        for record_id, payload_text in rows:
            if not isinstance(record_id, str) or not isinstance(payload_text, str):
                raise ValueError(f"invalid v4 row in {collection}")
            payload = decode_json_value(payload_text)
            if not isinstance(payload, dict):
                raise ValueError(f"invalid v4 payload in {collection}")
            record = cast(dict[str, object], payload)
            decoded.append((record_id, record))
            keys.update(record)
        for key in sorted(keys):
            if key != "id":
                connection.execute(
                    f"ALTER TABLE {_identifier(table)} "
                    f"ADD COLUMN {_identifier(key)} TEXT"
                )
        for record_id, record in decoded:
            columns = ("id",) + tuple(sorted(key for key in record if key != "id"))
            values = (record_id,) + tuple(
                encode_json_value(
                    record[key],
                    ensure_ascii=True,
                    separators=(",", ":"),
                )
                for key in columns[1:]
            )
            connection.execute(
                f"INSERT INTO {_identifier(table)} "
                f"({', '.join(_identifier(column) for column in columns)}) "
                f"VALUES ({', '.join('?' for _ in columns)})",
                values,
            )
    connection.execute("DROP TABLE workspace_entries")
    connection.execute("DROP TABLE records")
