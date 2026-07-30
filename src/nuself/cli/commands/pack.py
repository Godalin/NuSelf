"""Thought-pack archive command handlers."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from nuself.config import runtime_paths
from nuself.private_fs import ensure_private_directory
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.storage import get_default_backend
from nuself.storage_sqlite import (
    SqliteStorageBackend,
    ThoughtPackValidationError,
    import_sqlite_thought_pack,
    inspect_sqlite_thought_pack,
)

_PACK_EXPORT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_WINDOWS_DEVICE_NAME = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$",
    re.IGNORECASE,
)


def handle_pack_export(args: argparse.Namespace) -> int:
    paths = runtime_paths(args.project_root)
    source = paths.authority_root / "nuself.sqlite"
    if not source.exists():
        print(
            "No nuself.sqlite authority found. Run 'nuself init' first.",
            file=sys.stderr,
        )
        return 1
    exports = paths.authority_root / "exports"
    ensure_private_directory(exports)
    name = args.name.removesuffix(".sqlite")
    if not _is_portable_pack_name(name):
        print(
            "Invalid pack name: use letters, digits, '.', '_', or '-' "
            "and start with a letter or digit.",
            file=sys.stderr,
        )
        return 1
    destination = exports / f"{name}.sqlite"
    backend = get_default_backend(args.project_root)
    if not isinstance(backend, SqliteStorageBackend):
        raise RuntimeError(
            "nuself.sqlite exists but the active backend is not SQLite"
        )
    backend.backup_to(destination, managed=True)
    print(f"Exported to {destination}")
    return 0


def _is_portable_pack_name(name: str) -> bool:
    if _PACK_EXPORT_NAME.fullmatch(name) is None or name.endswith("."):
        return False
    first_component = name.split(".", maxsplit=1)[0]
    return _WINDOWS_DEVICE_NAME.fullmatch(first_component) is None


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
    ).authority_root / "imports"
    ensure_private_directory(imports)
    destination = imports / source.name
    if destination.exists():
        print(
            f"Already imported: {destination.name}",
            file=sys.stderr,
        )
        return 1
    try:
        import_sqlite_thought_pack(
            source,
            destination,
            managed=True,
        )
    except ThoughtPackValidationError as exc:
        print(
            "Invalid thought pack: "
            f"{diagnostic_exception_message(exc)}",
            file=sys.stderr,
        )
        return 1
    print(f"Imported to {destination}")
    return 0


def _format_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.0f}K"
    return f"{size / 1024 / 1024:.1f}M"


def handle_pack_list(args: argparse.Namespace) -> int:
    authority_root = runtime_paths(args.project_root).authority_root
    for subdirectory, label in (
        ("imports", "Imports"),
        ("exports", "Exports"),
    ):
        directory = authority_root / subdirectory
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
    authority_root = runtime_paths(project_root).authority_root
    if name is None:
        database = authority_root / "nuself.sqlite"
        if not database.exists():
            print("No nuself.sqlite found.", file=sys.stderr)
            return None
        return database
    candidates = (
        Path(name).resolve(),
        authority_root / "imports" / f"{name}.sqlite",
        authority_root / "exports" / f"{name}.sqlite",
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
    try:
        inspection = inspect_sqlite_thought_pack(database)
    except ThoughtPackValidationError as exc:
        print(
            "Invalid thought pack: "
            f"{diagnostic_exception_message(exc)}",
            file=sys.stderr,
        )
        return 1
    print(f"Thought pack: {database.name}")
    print(f"  path: {database}")
    print(f"  collections: {len(inspection.collection_counts)}")
    for name, count in sorted(inspection.collection_counts):
        if count:
            print(f"    {name}: {count} items")
    print(f"  total items: {inspection.total_items}")
    return 0
