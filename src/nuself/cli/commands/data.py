"""Validated user-facing inspection and editing of SQLite records."""

from __future__ import annotations

import argparse
import difflib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from typing import Callable, cast

from nuself.agent.chat import ThreadState
from nuself.cli.control import ConfirmationDecision, read_confirmation
from nuself.cli.exit_codes import CliExitCode
from nuself.domain.memory import MemoryEntry
from nuself.private_fs import ensure_private_directory
from nuself.runtime import decode_json_value, encode_json_value
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.config import runtime_paths
from nuself.logs import write_log_event
from nuself.storage import COLLECTION_NAMES, get_default_backend


_PUBLIC_ALIASES: dict[str, str] = {
    "memory": "memory_entries",
    "candidates": "memory_candidates",
    "threads": "chat_threads",
    "profile": "profile_items",
    "sources": "source_documents",
    "source-chunks": "source_chunks",
    "persona": "persona_prompts",
    "reason-threads": "reason_threads",
    "reason-steps": "reason_steps",
    "traces": "trace_nodes",
    "trace-edges": "trace_edges",
    "notifications": "notification_outbox",
    "reflections": "reflection_entries",
}
_INTERNAL_COLLECTIONS = {
    "memory_curator_cursors",
    "memory_curator_plans",
    "scheduler_state",
}
_VALIDATORS: dict[str, Callable[[dict[str, object]], object]] = {
    "memory_entries": MemoryEntry.from_wire,
    "chat_threads": ThreadState.from_wire,
}


def _write_change_audit(
    *,
    action: str,
    collection: str,
    record_id: str,
    project_root: Path | None,
) -> None:
    try:
        write_log_event(
            "daemon",
            f"data_record_{action}",
            f"Authoritative data record {action}",
            project_root=project_root,
            status="completed",
            metadata={
                "collection": collection,
                "record_id": record_id,
            },
        )
    except Exception as exc:
        print(
            "Warning: data change committed but audit logging failed: "
            f"{diagnostic_exception_message(exc)}",
            file=sys.stderr,
        )


def _collection_name(value: str, *, internal: bool) -> str:
    name = _PUBLIC_ALIASES.get(value, value)
    if name not in COLLECTION_NAMES:
        raise ValueError(f"unknown data collection: {value}")
    if name in _INTERNAL_COLLECTIONS and not internal:
        raise ValueError(
            f"internal collection requires --internal: {value}"
        )
    return name


def _record_id(record: dict[str, object]) -> str:
    value = record.get("id", record.get("thread_id"))
    return value if isinstance(value, str) else "<invalid-id>"


def _json_text(value: object, *, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        ) + "\n"
    return encode_json_value(value, ensure_ascii=True)


def handle_data_collections(args: argparse.Namespace) -> int:
    writable = set(_VALIDATORS)
    for alias, name in _PUBLIC_ALIASES.items():
        mode = "editable" if name in writable else "read-only"
        print(f"{alias}\t{name}\t{mode}")
    if args.internal:
        for name in sorted(_INTERNAL_COLLECTIONS):
            print(f"{name}\t{name}\tread-only")
    return 0


def handle_data_list(args: argparse.Namespace) -> int:
    try:
        name = _collection_name(args.collection, internal=args.internal)
    except ValueError as exc:
        print(diagnostic_exception_message(exc), file=sys.stderr)
        return 1
    records = get_default_backend(args.project_root).collection(name).list()
    if args.json:
        for record in records:
            print(_json_text(record))
        return 0
    if not records:
        print(f"No records in {args.collection}.")
        return 0
    for record in records:
        fields = sorted(key for key in record if key != "id")
        print(
            f"{_record_id(record)}"
            + (f"\tfields={','.join(fields)}" if fields else "")
        )
    return 0


def handle_data_show(args: argparse.Namespace) -> int:
    try:
        name = _collection_name(args.collection, internal=args.internal)
    except ValueError as exc:
        print(diagnostic_exception_message(exc), file=sys.stderr)
        return 1
    record = get_default_backend(args.project_root).collection(name).get(
        args.record_id
    )
    if record is None:
        print(
            f"Record not found: {args.collection}/{args.record_id}",
            file=sys.stderr,
        )
        return 1
    print(_json_text(record) if args.json else _json_text(record, pretty=True), end="")
    return 0


def handle_data_check(args: argparse.Namespace) -> int:
    """Validate raw records and point to explicit repair operations."""

    try:
        name = _collection_name(args.collection, internal=args.internal)
        validator = _VALIDATORS.get(name)
        if validator is None:
            raise ValueError(
                "collection has no generic validation contract: "
                f"{args.collection}"
            )
    except ValueError as exc:
        print(
            f"Data check failed: {diagnostic_exception_message(exc)}",
            file=sys.stderr,
        )
        return CliExitCode.FAILURE

    records = get_default_backend(args.project_root).collection(name).list()
    invalid_ids: list[str] = []
    for record in records:
        try:
            validator(record)
        except (KeyError, TypeError, ValueError):
            invalid_ids.append(_record_id(record))

    healthy_count = len(records) - len(invalid_ids)
    print(
        f"Checked {len(records)} {args.collection} record(s): "
        f"{healthy_count} valid, {len(invalid_ids)} invalid."
    )
    for record_id in invalid_ids:
        print(f"Invalid: {record_id}")
        if record_id != "<invalid-id>":
            edit = shlex.join(
                ["nuself", "data", "edit", args.collection, record_id]
            )
            delete = shlex.join(
                ["nuself", "data", "delete", args.collection, record_id]
            )
            print(f"  repair: {edit}")
            print(f"  remove: {delete}")
    return (
        CliExitCode.FAILURE
        if invalid_ids
        else CliExitCode.SUCCESS
    )


def _repair_legacy_memory_record(
    record: dict[str, object],
) -> dict[str, object] | None:
    repaired = dict(record)
    changed = False
    for field in ("related_memory_ids", "supersedes"):
        if field not in repaired:
            continue
        if repaired[field] != []:
            return None
        del repaired[field]
        changed = True
    if not changed:
        return None
    MemoryEntry.from_wire(repaired)
    return repaired


def handle_data_repair(args: argparse.Namespace) -> int:
    """Preview or apply only explicitly supported lossless migrations."""

    try:
        name = _collection_name(args.collection, internal=False)
        if name != "memory_entries":
            raise ValueError(
                f"collection has no automatic repair migration: "
                f"{args.collection}"
            )
        backend = get_default_backend(args.project_root)
        collection = backend.collection(name)
        originals: dict[str, dict[str, object]] = {}
        repaired_records: dict[str, dict[str, object]] = {}
        unresolved: list[str] = []
        for record in collection.list():
            try:
                MemoryEntry.from_wire(record)
                continue
            except (KeyError, TypeError, ValueError):
                pass
            record_id = _record_id(record)
            repaired = _repair_legacy_memory_record(record)
            if repaired is None or record_id == "<invalid-id>":
                unresolved.append(record_id)
                continue
            originals[record_id] = record
            repaired_records[record_id] = repaired

        print(
            f"Repair scan: {len(repaired_records)} repairable, "
            f"{len(unresolved)} unresolved."
        )
        if not args.apply:
            if repaired_records:
                print(
                    "No changes applied. Run "
                    f"`nuself data repair {args.collection} --apply`."
                )
            return (
                CliExitCode.FAILURE
                if unresolved
                else CliExitCode.SUCCESS
            )

        with backend.transaction():
            for record_id, original in originals.items():
                if collection.get(record_id) != original:
                    raise ValueError(
                        f"record changed concurrently: {record_id}"
                    )
            for record_id, repaired in repaired_records.items():
                collection.put(record_id, repaired)
        for record_id in repaired_records:
            _write_change_audit(
                action="updated",
                collection=name,
                record_id=record_id,
                project_root=args.project_root,
            )
        print(f"Repaired {len(repaired_records)} record(s).")
        if unresolved:
            print(
                "Unresolved records still require `nuself data check memory`.",
                file=sys.stderr,
            )
            return CliExitCode.FAILURE
        return CliExitCode.SUCCESS
    except (OSError, TypeError, ValueError) as exc:
        print(
            f"Data repair failed: {diagnostic_exception_message(exc)}",
            file=sys.stderr,
        )
        return CliExitCode.FAILURE


def _load_edited_record(args: argparse.Namespace, current: str) -> str:
    if args.file is not None:
        return args.file.read_text(encoding="utf-8")
    paths = runtime_paths(args.project_root)
    ensure_private_directory(paths.runtime_dir)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="data-edit-",
        suffix=".json",
        dir=paths.runtime_dir,
        text=True,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(current, encoding="utf-8")
        editor = args.editor or os.environ.get("EDITOR") or "vi"
        subprocess.run(
            [*shlex.split(editor), str(temporary)],
            check=True,
        )
        return temporary.read_text(encoding="utf-8")
    finally:
        temporary.unlink(missing_ok=True)


def handle_data_edit(args: argparse.Namespace) -> int:
    try:
        name = _collection_name(args.collection, internal=args.internal)
        validator = _VALIDATORS.get(name)
        if validator is None:
            raise ValueError(
                f"collection is read-only through generic editing: "
                f"{args.collection}"
            )
        backend = get_default_backend(args.project_root)
        collection = backend.collection(name)
        original = collection.get(args.record_id)
        if original is None:
            raise ValueError(
                f"record not found: {args.collection}/{args.record_id}"
            )
        original_text = _json_text(original, pretty=True)
        edited_text = _load_edited_record(args, original_text)
        decoded = decode_json_value(edited_text)
        if not isinstance(decoded, dict):
            raise ValueError("edited record must be a JSON object")
        edited = cast(dict[str, object], decoded)
        identity = edited.get("id", edited.get("thread_id"))
        if identity != args.record_id:
            raise ValueError("edited record cannot change its stable identity")
        validator(edited)
        if edited == original:
            print("No changes.")
            return 0
        diff = "".join(
            difflib.unified_diff(
                original_text.splitlines(keepends=True),
                _json_text(edited, pretty=True).splitlines(keepends=True),
                fromfile="stored",
                tofile="edited",
            )
        )
        print(diff, end="")
        if not args.yes:
            decision = read_confirmation("Apply changes? [y/N] ")
            if decision is ConfirmationDecision.INTERRUPTED:
                return CliExitCode.INTERRUPTED
            if decision is ConfirmationDecision.NO:
                print("Cancelled.")
                return CliExitCode.FAILURE
        with backend.transaction():
            if collection.get(args.record_id) != original:
                raise ValueError(
                    "record changed concurrently; reload before editing"
                )
            collection.put(args.record_id, edited)
        _write_change_audit(
            action="updated",
            collection=name,
            record_id=args.record_id,
            project_root=args.project_root,
        )
        print(f"Updated {args.collection}/{args.record_id}.")
        return 0
    except (
        OSError,
        subprocess.SubprocessError,
        TypeError,
        ValueError,
    ) as exc:
        print(
            "Data edit failed: "
            f"{diagnostic_exception_message(exc)}",
            file=sys.stderr,
        )
        return 1


def handle_data_delete(args: argparse.Namespace) -> int:
    try:
        name = _collection_name(args.collection, internal=args.internal)
        if name not in _VALIDATORS:
            raise ValueError(
                f"collection is read-only through generic deletion: "
                f"{args.collection}"
            )
        backend = get_default_backend(args.project_root)
        collection = backend.collection(name)
        if collection.get(args.record_id) is None:
            raise ValueError(
                f"record not found: {args.collection}/{args.record_id}"
            )
        if not args.yes:
            decision = read_confirmation("Delete permanently? [y/N] ")
            if decision is ConfirmationDecision.INTERRUPTED:
                return CliExitCode.INTERRUPTED
            if decision is ConfirmationDecision.NO:
                print("Cancelled.")
                return CliExitCode.FAILURE
        with backend.transaction():
            collection.delete(args.record_id)
        _write_change_audit(
            action="deleted",
            collection=name,
            record_id=args.record_id,
            project_root=args.project_root,
        )
        print(f"Deleted {args.collection}/{args.record_id}.")
        return 0
    except ValueError as exc:
        print(
            "Data delete failed: "
            f"{diagnostic_exception_message(exc)}",
            file=sys.stderr,
        )
        return 1


def handle_data_export(args: argparse.Namespace) -> int:
    try:
        name = _collection_name(args.collection, internal=args.internal)
    except ValueError as exc:
        print(diagnostic_exception_message(exc), file=sys.stderr)
        return 1
    records = get_default_backend(args.project_root).collection(name).list()
    if args.format == "json":
        content = _json_text(list(records), pretty=True)
    else:
        content = "".join(f"{_json_text(record)}\n" for record in records)
    if args.output is None:
        print(content, end="")
    else:
        args.output.write_text(content, encoding="utf-8")
        print(f"Exported {len(records)} records to {args.output}.")
    return 0
