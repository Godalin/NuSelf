#!/usr/bin/env python3
"""Import legacy reason workspaces into the schema-v4 authority."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from nuself.private_fs import (
    ensure_private_directory,
    ensure_private_file,
    require_private_file,
)
from nuself.runtime import decode_json_value, encode_json_value
from scripts.database_migrations.schema_identity import validate_schema


def _put(
    connection: sqlite3.Connection,
    namespace: str,
    key: str,
    value: str,
    created_at: str,
    updated_at: str,
) -> None:
    decoded = decode_json_value(value)
    if not isinstance(decoded, dict):
        raise ValueError(f"workspace value {namespace}/{key} is not an object")
    encoded = encode_json_value(
        cast(dict[str, object], decoded),
        ensure_ascii=True,
        separators=(",", ":"),
    )
    existing = connection.execute(
        "SELECT value FROM workspace_entries WHERE namespace=? AND key=?",
        (namespace, key),
    ).fetchone()
    if existing is not None:
        if existing[0] != encoded:
            raise ValueError(f"workspace conflict at {namespace}/{key}")
        return
    connection.execute(
        "INSERT INTO workspace_entries "
        "(namespace,key,value,created_at,updated_at) VALUES (?,?,?,?,?)",
        (namespace, key, encoded, created_at, updated_at),
    )


def migrate(
    authority: Path,
    *,
    target: str = "main",
    apply: bool,
    delete_source: bool = False,
) -> tuple[int, int]:
    if target == "legacy":
        return _restore_legacy(authority, apply=apply, delete_source=delete_source)
    if target != "main":
        raise ValueError("workspace target must be 'main' or 'legacy'")
    legacy = authority / "workspaces" / "reason"
    if legacy.is_symlink():
        raise ValueError("legacy workspace root must not be a symlink")
    owners = (
        tuple(path for path in sorted(legacy.iterdir()) if path.is_dir())
        if legacy.is_dir()
        else ()
    )
    entries = 0
    files = 0
    database = authority / "nuself.sqlite"
    require_private_file(database)
    connection = sqlite3.connect(database)
    try:
        if validate_schema(connection) not in (4, 5):
            raise ValueError("workspace migration requires compact schema v4+")
        connection.execute("BEGIN IMMEDIATE")
        for owner in owners:
            thread_id = owner.name
            source_db = owner / "workspace.sqlite"
            if source_db.is_file():
                source = sqlite3.connect(
                    f"{source_db.resolve().as_uri()}?mode=ro", uri=True
                )
                try:
                    tables = {
                        row[0]
                        for row in source.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        )
                    }
                    source_table = (
                        "workspace_entries"
                        if "workspace_entries" in tables
                        else "items"
                    )
                    for namespace, key, value, created, updated in source.execute(
                        "SELECT namespace,key,value,created_at,updated_at "
                        f"FROM {source_table}"
                    ):
                        if namespace == f"workspace/{thread_id}":
                            namespace = f"workspace/reason/{thread_id}"
                        if apply:
                            _put(connection, namespace, key, value, created, updated)
                        entries += 1
                finally:
                    source.close()
            persona_dir = owner / "persona_prompts"
            for item in sorted(persona_dir.glob("*.json")):
                if item.name == "name_index.json":
                    continue
                timestamp = datetime.fromtimestamp(item.stat().st_mtime, UTC).isoformat()
                if apply:
                    _put(
                        connection,
                        f"workspace/reason/{thread_id}/persona_prompts",
                        item.stem,
                        item.read_text(encoding="utf-8"),
                        timestamp,
                        timestamp,
                    )
                entries += 1
            source_exports = owner / "artifacts" / "export"
            for item in source_exports.rglob("*") if source_exports.is_dir() else ():
                if not item.is_file():
                    continue
                destination = (
                    authority / "exports" / "reason" / thread_id
                    / item.relative_to(source_exports)
                )
                if apply:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if destination.exists():
                        if destination.read_bytes() != item.read_bytes():
                            raise FileExistsError(destination)
                    else:
                        shutil.copy2(item, destination)
                files += 1
        connection.commit() if apply else connection.rollback()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
    if apply and delete_source and owners:
        shutil.rmtree(legacy.parent)
    return entries, files


def _restore_legacy(
    authority: Path,
    *,
    apply: bool,
    delete_source: bool,
) -> tuple[int, int]:
    database = authority / "nuself.sqlite"
    require_private_file(database)
    connection = sqlite3.connect(database)
    legacy_root = authority / "workspaces"
    exports_root = authority / "exports" / "reason"
    created_legacy = False
    try:
        if validate_schema(connection) not in (4, 5):
            raise ValueError("workspace migration requires compact schema v4+")
        rows = connection.execute(
            "SELECT namespace,key,value,created_at,updated_at "
            "FROM workspace_entries "
            "WHERE namespace LIKE 'workspace/reason/%'"
        ).fetchall()
        owners = {
            namespace.split("/")[2]
            for namespace, *_ in rows
            if len(namespace.split("/")) >= 3
        }
        if not apply:
            return len(rows), len(owners)
        if legacy_root.exists() or legacy_root.is_symlink():
            raise FileExistsError(legacy_root)
        connection.execute("BEGIN IMMEDIATE")
        created_legacy = True
        for owner_id in sorted(owners):
            root = legacy_root / "reason" / owner_id
            ensure_private_directory(root)
            database_path = root / "workspace.sqlite"
            ensure_private_file(database_path)
            legacy = sqlite3.connect(database_path)
            try:
                legacy.execute(
                    "CREATE TABLE workspace_entries ("
                    "namespace TEXT NOT NULL, key TEXT NOT NULL, "
                    "value TEXT NOT NULL, created_at TEXT NOT NULL, "
                    "updated_at TEXT NOT NULL, "
                    "PRIMARY KEY(namespace,key))"
                )
                legacy.executemany(
                    "INSERT INTO workspace_entries VALUES (?,?,?,?,?)",
                    tuple(
                        row
                        for row in rows
                        if row[0].split("/")[2] == owner_id
                    ),
                )
                legacy.commit()
            finally:
                legacy.close()
            export_source = authority / "exports" / "reason" / owner_id
            if export_source.is_dir():
                export_destination = root / "artifacts" / "export"
                shutil.copytree(export_source, export_destination)
                for source in export_source.rglob("*"):
                    if source.is_file():
                        restored = (
                            export_destination
                            / source.relative_to(export_source)
                        )
                        if restored.read_bytes() != source.read_bytes():
                            raise RuntimeError(
                                f"export verification failed: {restored}"
                            )
        if delete_source:
            connection.execute(
                "DELETE FROM workspace_entries "
                "WHERE namespace LIKE 'workspace/reason/%'"
            )
        connection.commit()
        if delete_source and exports_root.exists():
            shutil.rmtree(exports_root)
        return len(rows), len(owners)
    except BaseException:
        connection.rollback()
        if created_legacy and legacy_root.exists():
            shutil.rmtree(legacy_root)
        raise
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("authority", type=Path)
    parser.add_argument("--to", choices=("main", "legacy"), default="main")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--delete-source", action="store_true")
    args = parser.parse_args()
    entries, second = migrate(
        args.authority.absolute(),
        target=args.to,
        apply=args.apply,
        delete_source=args.delete_source,
    )
    if args.apply:
        print(f"migrated {entries} workspace row(s)")
    else:
        print(f"planned {entries} workspace row(s) across {second} owner(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
