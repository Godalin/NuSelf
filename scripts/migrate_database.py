#!/usr/bin/env python3
"""Explicitly migrate one NuSelf SQLite authority to a requested version."""

from __future__ import annotations

import argparse
import fcntl
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from nuself.private_fs import (
    PRIVATE_FILE_MODE,
    ensure_managed_directory,
    harden_managed_file,
    require_private_file,
)
from scripts.database_migrations.model import Direction
from scripts.database_migrations.registry import CURRENT_VERSION, migration_plan
from scripts.database_migrations.schema_identity import validate_schema


def _managed(database: Path) -> bool:
    return (
        database.name == "nuself.sqlite"
        and database.parent.name == ".nuself"
    )


def _prepare_database(database: Path, *, managed: bool) -> None:
    if managed:
        ensure_managed_directory(database.parent, database.parent)
        harden_managed_file(database.parent, database)
    else:
        require_private_file(database)


def _create_backup_file(path: Path, *, managed: bool) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        PRIVATE_FILE_MODE if managed else 0o666,
    )
    try:
        if managed:
            os.fchmod(descriptor, PRIVATE_FILE_MODE)
    finally:
        os.close(descriptor)


def _backup(
    connection: sqlite3.Connection,
    destination: Path,
    *,
    managed: bool,
) -> None:
    _create_backup_file(destination, managed=managed)
    try:
        backup_connection = sqlite3.connect(destination)
        try:
            connection.backup(backup_connection)
        finally:
            backup_connection.close()
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


@contextmanager
def _lease(database: Path, *, managed: bool) -> Generator[None, None, None]:
    lock_path = database.with_name(f"{database.name}.schema.lock")
    descriptor = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
        0o600 if managed else 0o666,
    )
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def migrate(database: Path, target_version: int, *, dry_run: bool) -> tuple[str, ...]:
    managed = _managed(database)
    _prepare_database(database, managed=managed)
    with _lease(database, managed=managed):
        connection = sqlite3.connect(database)
        try:
            current_version = validate_schema(connection)
            selected = migration_plan(current_version, target_version)
            descriptions = tuple(
                f"{step.direction.value} {step.migration.migration_id}"
                for step in selected.steps
            )
            if dry_run or not selected.steps:
                return descriptions
            backup = database.with_name(
                f"{database.name}.pre-v{current_version}-to-v{target_version}.bak"
            )
            _backup(connection, backup, managed=managed)
            connection.execute("BEGIN IMMEDIATE")
            try:
                for step in selected.steps:
                    operation = (
                        step.migration.upgrade
                        if step.direction is Direction.UPGRADE
                        else step.migration.downgrade
                    )
                    if operation is None:
                        raise RuntimeError("planned migration operation is missing")
                    operation(connection)
                    if step.direction is Direction.UPGRADE:
                        connection.execute(
                            "INSERT INTO _schema_version (version) VALUES (?)",
                            (step.destination_version,),
                        )
                    else:
                        connection.execute(
                            "DELETE FROM _schema_version WHERE version = ?",
                            (step.migration.to_version,),
                        )
                migrated_version = validate_schema(connection)
                if migrated_version != target_version:
                    raise RuntimeError(
                        "migration did not produce the requested schema version"
                    )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            return descriptions
        finally:
            connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--to", type=int, default=CURRENT_VERSION)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    steps = migrate(args.database.expanduser().absolute(), args.to, dry_run=args.dry_run)
    if not steps:
        print(f"Database is already at schema v{args.to}.")
    else:
        for step in steps:
            print(step)
        if not args.dry_run:
            print(f"Database migrated to schema v{args.to}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
