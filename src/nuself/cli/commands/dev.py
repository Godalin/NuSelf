"""Developer storage inspection and migration command handlers."""

from __future__ import annotations

import argparse
from contextlib import closing

from nuself.storage import (
    create_file_backend,
    create_sqlite_backend,
    get_default_backend,
    migrate_all,
)
from nuself.storage_sqlite import SqliteStorageBackend


def handle_dev_migrate(args: argparse.Namespace) -> int:
    source = create_file_backend(args.project_root)
    with closing(
        create_sqlite_backend(args.project_root, db_path=args.db)
    ) as destination:
        result = migrate_all(
            source, destination, clear_dst=args.clear
        )
        if result:
            for name, count in sorted(result.items()):
                print(f"  {name}: {count} items")
        else:
            print("  (no data to migrate)")
        total = sum(result.values())
        print(
            f"Migrated {total} items across {len(result)} "
            f"collections to {destination.db_path}"
        )
    return 0


def handle_dev_db_schema(args: argparse.Namespace) -> int:
    with closing(
        create_sqlite_backend(args.project_root)
    ) as backend:
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
    backend = get_default_backend(args.project_root)
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
    root = getattr(backend, "_root", None)
    if root is not None:
        print("Active backend: FileStorageBackend")
        print(f"  file root: {root}")
    else:
        print(f"Active backend: {type(backend).__name__}")
    return 0
