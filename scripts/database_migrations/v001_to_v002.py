"""Historical v1→v2 migration: payload blobs to dynamic columns."""

from __future__ import annotations

import sqlite3
from typing import cast

from nuself.runtime.messages import decode_json_value, encode_json_value
from scripts.database_migrations.schema_identity import SCHEMA_COLLECTIONS

COLLECTIONS = SCHEMA_COLLECTIONS[1]


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def upgrade(connection: sqlite3.Connection) -> None:
    for name in COLLECTIONS:
        table = f"col_{name}"
        columns = [
            row[1]
            for row in connection.execute(
                f"PRAGMA table_info({_identifier(table)})"
            ).fetchall()
        ]
        if "payload" not in columns:
            continue
        rows = connection.execute(
            f"SELECT id, payload FROM {_identifier(table)}"
        ).fetchall()
        records: list[tuple[str, dict[str, object]]] = []
        keys: set[str] = set()
        for row_id, payload_text in rows:
            if not isinstance(row_id, str) or not isinstance(payload_text, str):
                raise ValueError(f"invalid v1 row in {name!r}")
            decoded = decode_json_value(payload_text)
            if not isinstance(decoded, dict):
                raise ValueError(f"invalid v1 payload in {name!r}")
            record = {
                str(key): value
                for key, value in cast(dict[object, object], decoded).items()
            }
            if record.get("id", row_id) != row_id:
                raise ValueError(f"v1 payload ID mismatch in {name!r}")
            record["id"] = row_id
            records.append((row_id, record))
            keys.update(key for key in record if key != "id")
        for key in sorted(keys):
            if key not in columns:
                connection.execute(
                    f"ALTER TABLE {_identifier(table)} "
                    f"ADD COLUMN {_identifier(key)} TEXT"
                )
        for row_id, record in records:
            for key, value in record.items():
                if key != "id":
                    connection.execute(
                        f"UPDATE {_identifier(table)} "
                        f"SET {_identifier(key)} = ? WHERE id = ?",
                        (encode_json_value(value, ensure_ascii=True), row_id),
                    )
        connection.execute(
            f"ALTER TABLE {_identifier(table)} DROP COLUMN payload"
        )
