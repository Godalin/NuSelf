"""Manually migrate pre-v0.3.1 memory records to the current wire shape."""

from __future__ import annotations

import argparse
from pathlib import Path

from nuself.domain.memory import MemoryEntry
from nuself.storage import get_default_backend, reset_default_backend


def migrate_record(record: dict[str, object]) -> dict[str, object] | None:
    """Return one losslessly normalized record, or None when unsupported."""

    repaired = dict(record)
    changed = False
    for field in ("related_memory_ids", "supersedes"):
        if field not in repaired:
            continue
        if repaired[field] != []:
            return None
        del repaired[field]
        changed = True
    if "relations" not in repaired:
        repaired["relations"] = {}
        changed = True
    if not changed:
        return None
    MemoryEntry.from_wire(repaired)
    return repaired


def run(authority_root: Path, *, apply: bool) -> int:
    backend = get_default_backend(authority_root)
    collection = backend.collection("memory_entries")
    originals: dict[str, dict[str, object]] = {}
    migrations: dict[str, dict[str, object]] = {}
    unresolved: list[str] = []
    try:
        for record in collection.list():
            try:
                MemoryEntry.from_wire(record)
                continue
            except (KeyError, TypeError, ValueError):
                pass
            record_id = record.get("id")
            migrated = migrate_record(record)
            if not isinstance(record_id, str) or migrated is None:
                unresolved.append(
                    record_id if isinstance(record_id, str) else "<invalid-id>"
                )
                continue
            originals[record_id] = record
            migrations[record_id] = migrated

        print(
            f"Migration scan: {len(migrations)} migratable, "
            f"{len(unresolved)} unresolved."
        )
        for record_id in unresolved:
            print(f"Unresolved: {record_id}")
        if not apply:
            if migrations:
                print("Dry run only; rerun with --apply to commit.")
            return 1 if unresolved else 0

        with backend.transaction():
            for record_id, original in originals.items():
                if collection.get(record_id) != original:
                    raise RuntimeError(
                        f"record changed concurrently: {record_id}"
                    )
            for record_id, migrated in migrations.items():
                collection.put(record_id, migrated)
        print(f"Migrated {len(migrations)} record(s).")
        return 1 if unresolved else 0
    finally:
        reset_default_backend(authority_root)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate legacy memory records in one explicit NuSelf authority."
        )
    )
    parser.add_argument(
        "--authority-root",
        type=Path,
        required=True,
        help="Authority directory containing nuself.sqlite.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit supported migrations; the default is a dry run.",
    )
    args = parser.parse_args()
    return run(args.authority_root.expanduser().absolute(), apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
