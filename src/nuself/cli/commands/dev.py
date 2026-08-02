"""Developer storage inspection and migration command handlers."""

from __future__ import annotations

import argparse
import sys

from nuself.cli.application import cli_backend
from nuself.storage_sqlite import SqliteStorageBackend


def handle_dev_db_schema(args: argparse.Namespace) -> int:
    backend = cli_backend()
    if not isinstance(backend, SqliteStorageBackend):
        print(
            "No active SQLite database. Run 'nuself init' first.",
            file=sys.stderr,
        )
        return 1
    tables = backend.collection_names()
    if not tables:
        print("(no tables)")
        return 0
    for table in sorted(tables):
        print(f"{table}:")
        for (
            column_name,
            column_type,
            not_null,
            default_value,
            primary_key,
        ) in backend.table_info(table):
            nullable = "" if not_null else " NULL"
            pk_flag = " PK" if primary_key else ""
            default = (
                f" DEFAULT {default_value}"
                if default_value is not None
                else ""
            )
            print(
                f"  {column_name}  {column_type}"
                f"{nullable}{pk_flag}{default}"
            )
    return 0


def handle_dev_storage(args: argparse.Namespace) -> int:
    backend = cli_backend()
    if isinstance(backend, SqliteStorageBackend):
        print("Active backend: SqliteStorageBackend")
        print(f"  database: {backend.db_path}")
        tables = backend.collection_names()
        print(f"  collections: {len(tables)}")
        for name in sorted(tables):
            count = len(backend.collection(name).list())
            if count:
                print(f"    {name}: {count} items")
        return 0
    raise TypeError("default storage backend must be SQLite")
