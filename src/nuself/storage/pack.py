"""Explicit validation, inspection, and import of SQLite thought packs."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.storage.contract import COLLECTION_NAMES
from nuself.storage.sqlite import (
    SqliteSchemaValidationError,
    backup_connection_to_path,
    validate_nuself_schema,
)


class ThoughtPackValidationError(ValueError):
    """An external SQLite file is not a compatible thought pack."""


@dataclass(frozen=True)
class ThoughtPackInspection:
    """Read-only metadata for one validated thought pack."""

    schema_version: int
    collection_counts: tuple[tuple[str, int], ...]

    @property
    def total_items(self) -> int:
        return sum(count for _, count in self.collection_counts)


def import_sqlite_thought_pack(
    source: Path,
    destination: Path,
    *,
    managed: bool = False,
) -> int:
    """Validate and atomically import one external thought-pack snapshot."""

    temporary = destination.with_name(
        f".{destination.name}.{uuid4().hex}.tmp"
    )
    with _readonly_thought_pack(source) as source_connection:
        try:
            version = _validate_thought_pack_connection(source_connection)
            backup_connection_to_path(
                source_connection,
                temporary,
                managed=managed,
            )
            temporary.replace(destination)
            return version
        finally:
            temporary.unlink(missing_ok=True)


def inspect_sqlite_thought_pack(source: Path) -> ThoughtPackInspection:
    """Validate and inspect one thought pack without modifying it."""

    with _readonly_thought_pack(source) as connection:
        version = _validate_thought_pack_connection(connection)
        counts = tuple(
            (name, _collection_count(connection, name))
            for name in COLLECTION_NAMES
        )
    return ThoughtPackInspection(version, counts)


@contextmanager
def _readonly_thought_pack(
    source: Path,
) -> Generator[sqlite3.Connection, None, None]:
    source_uri = f"{source.resolve().as_uri()}?mode=ro"
    try:
        connection = sqlite3.connect(source_uri, uri=True)
    except sqlite3.DatabaseError as exc:
        raise ThoughtPackValidationError(
            "thought pack is not a readable SQLite database"
        ) from exc
    try:
        yield connection
    finally:
        connection.close()


def _validate_thought_pack_connection(
    connection: sqlite3.Connection,
) -> int:
    try:
        check_rows = connection.execute("PRAGMA quick_check").fetchall()
        if not check_rows or any(
            len(row) != 1 or row[0] != "ok" for row in check_rows
        ):
            raise ThoughtPackValidationError(
                "thought pack failed SQLite quick_check"
            )
        return validate_nuself_schema(connection)
    except ThoughtPackValidationError:
        raise
    except SqliteSchemaValidationError as exc:
        raise ThoughtPackValidationError(
            diagnostic_exception_message(exc)
        ) from exc
    except sqlite3.DatabaseError as exc:
        raise ThoughtPackValidationError(
            "thought pack is not a valid SQLite database"
        ) from exc


def _collection_count(
    connection: sqlite3.Connection,
    collection_name: str,
) -> int:
    compact = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='records'"
    ).fetchone()
    if compact is not None:
        row = connection.execute(
            "SELECT COUNT(*) FROM records WHERE collection = ?",
            (collection_name,),
        ).fetchone()
    else:
        table = f"col_{collection_name}"
        row = connection.execute(
            f'SELECT COUNT(*) FROM "{table}"'
        ).fetchone()
    count = row[0] if row is not None and len(row) == 1 else None
    if type(count) is not int or count < 0:
        raise ThoughtPackValidationError(
            f"thought pack collection {collection_name} has an invalid count"
        )
    return count
