"""Thought-pack archive command handlers."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from nuself.config import runtime_paths
from nuself.storage import get_default_backend
from nuself.storage_sqlite import SqliteStorageBackend


def handle_pack_export(args: argparse.Namespace) -> int:
    paths = runtime_paths(args.project_root)
    source = paths.private_root / "nuself.sqlite"
    if not source.exists():
        print(
            "No nuself.sqlite found. Run 'nuself dev migrate' "
            "first.",
            file=sys.stderr,
        )
        return 1
    exports = paths.private_root / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    name = args.name.removesuffix(".sqlite")
    destination = (exports / name).with_suffix(".sqlite")
    backend = get_default_backend(args.project_root)
    if not isinstance(backend, SqliteStorageBackend):
        raise RuntimeError(
            "nuself.sqlite exists but the active backend is not SQLite"
        )
    backend.backup_to(destination)
    print(f"Exported to {destination}")
    return 0


def handle_pack_import(args: argparse.Namespace) -> int:
    source = args.path.resolve()
    if not source.exists():
        print(f"File not found: {source}", file=sys.stderr)
        return 1
    if source.suffix != ".sqlite":
        print(
            f"Expected .sqlite file, got: {source.suffix}",
            file=sys.stderr,
        )
        return 1
    imports = runtime_paths(
        args.project_root
    ).private_root / "imports"
    imports.mkdir(parents=True, exist_ok=True)
    destination = imports / source.name
    if destination.exists():
        print(
            f"Already imported: {destination.name}",
            file=sys.stderr,
        )
        return 1
    shutil.copy2(source, destination)
    print(f"Imported to {destination}")
    return 0


def _format_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.0f}K"
    return f"{size / 1024 / 1024:.1f}M"


def handle_pack_list(args: argparse.Namespace) -> int:
    private_root = runtime_paths(args.project_root).private_root
    for subdirectory, label in (
        ("imports", "Imports"),
        ("exports", "Exports"),
    ):
        directory = private_root / subdirectory
        if not directory.exists():
            continue
        files = sorted(directory.glob("*.sqlite"))
        if not files:
            continue
        print(f"{label}:")
        for path in files:
            print(
                f"  {path.stem}  "
                f"({_format_size(path.stat().st_size)})"
            )
    return 0


def _resolve_pack_path(
    name: str | None, project_root: Path | None
) -> Path | None:
    private_root = runtime_paths(project_root).private_root
    if name is None:
        database = private_root / "nuself.sqlite"
        if not database.exists():
            print("No nuself.sqlite found.", file=sys.stderr)
            return None
        return database
    candidates = (
        Path(name).resolve(),
        private_root / "imports" / f"{name}.sqlite",
        private_root / "exports" / f"{name}.sqlite",
    )
    for candidate in candidates:
        if candidate.exists() and candidate.suffix == ".sqlite":
            return candidate
    print(f"No pack found: {name}", file=sys.stderr)
    return None


def handle_pack_inspect(args: argparse.Namespace) -> int:
    database = _resolve_pack_path(args.name, args.project_root)
    if database is None:
        return 1
    backend = SqliteStorageBackend(database)
    try:
        tables = backend.collection_names()
        total = 0
        print(f"Thought pack: {database.name}")
        print(f"  path: {database}")
        print(f"  collections: {len(tables)}")
        for name in sorted(tables):
            count = len(backend.collection(name).list())
            if count:
                print(f"    {name}: {count} items")
                total += count
        print(f"  total items: {total}")
    finally:
        backend.close()
    return 0
