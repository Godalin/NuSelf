"""Schema v5↔v6: rename persistent chat threads to conversations."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from typing import cast


def _rename_key(
    value: dict[str, object], old: str, new: str
) -> None:
    if old not in value:
        return
    if new in value:
        raise ValueError(f"record contains both {old!r} and {new!r}")
    value[new] = value.pop(old)


def _walk_memory(value: object, *, upgrade: bool) -> object:
    old_kind, new_kind = (
        ("thread", "conversation")
        if upgrade
        else ("conversation", "thread")
    )
    old_prefix = f"{old_kind}:"
    new_prefix = f"{new_kind}:"
    if isinstance(value, dict):
        mapping = cast(dict[str, object], value)
        transformed: dict[str, object] = {}
        for key, item in mapping.items():
            if key == "source_type" and item == old_kind:
                transformed[key] = new_kind
            elif key == "source_ref" and isinstance(item, str) and item.startswith(old_prefix):
                transformed[key] = new_prefix + item[len(old_prefix) :]
            elif key == "source_refs" and isinstance(item, list):
                transformed[key] = [
                    new_prefix + ref[len(old_prefix) :]
                    if isinstance(ref, str) and ref.startswith(old_prefix)
                    else ref
                    for ref in cast(list[object], item)
                ]
            else:
                transformed[key] = _walk_memory(item, upgrade=upgrade)
        return transformed
    if isinstance(value, list):
        items = cast(list[object], value)
        return [_walk_memory(item, upgrade=upgrade) for item in items]
    return value


def _conversation_record(value: dict[str, object], *, upgrade: bool) -> None:
    old, new = (
        ("thread_id", "conversation_id")
        if upgrade
        else ("conversation_id", "thread_id")
    )
    _rename_key(value, old, new)


def _trace_record(value: dict[str, object], *, upgrade: bool) -> None:
    _conversation_record(value, upgrade=upgrade)


def _reflection_record(value: dict[str, object], *, upgrade: bool) -> None:
    old, new = (
        ("suggested_thread_id", "suggested_conversation_id")
        if upgrade
        else ("suggested_conversation_id", "suggested_thread_id")
    )
    _rename_key(value, old, new)


def _notification_record(value: dict[str, object], *, upgrade: bool) -> None:
    old, new = (
        ("nuself://thread/", "nuself://conversation/")
        if upgrade
        else ("nuself://conversation/", "nuself://thread/")
    )
    deep_link = value.get("deep_link")
    if isinstance(deep_link, str) and deep_link.startswith(old):
        value["deep_link"] = new + deep_link[len(old) :]


def _transform_records(
    connection: sqlite3.Connection,
    *,
    upgrade: bool,
) -> None:
    old_collection, new_collection = (
        ("chat_threads", "conversations")
        if upgrade
        else ("conversations", "chat_threads")
    )
    collision = connection.execute(
        "SELECT 1 FROM records WHERE collection = ? LIMIT 1",
        (new_collection,),
    ).fetchone()
    if collision is not None:
        raise ValueError(
            f"destination collection already exists: {new_collection}"
        )

    transforms: dict[str, Callable[[dict[str, object]], None]] = {
        old_collection: lambda value: _conversation_record(
            value, upgrade=upgrade
        ),
        "memory_curator_cursors": lambda value: _conversation_record(
            value, upgrade=upgrade
        ),
        "memory_curator_plans": lambda value: _conversation_record(
            value, upgrade=upgrade
        ),
        "trace_nodes": lambda value: _trace_record(value, upgrade=upgrade),
        "reflection_entries": lambda value: _reflection_record(
            value, upgrade=upgrade
        ),
        "notification_outbox": lambda value: _notification_record(
            value, upgrade=upgrade
        ),
    }
    for collection, transform in transforms.items():
        rows = connection.execute(
            "SELECT id, payload FROM records WHERE collection = ?",
            (collection,),
        ).fetchall()
        for record_id, payload_text in rows:
            value = cast(object, json.loads(payload_text))
            if not isinstance(value, dict):
                raise ValueError("record payload must be a JSON object")
            record = cast(dict[str, object], value)
            transform(record)
            connection.execute(
                "UPDATE records SET payload = ? "
                "WHERE collection = ? AND id = ?",
                (
                    json.dumps(
                        record,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    collection,
                    record_id,
                ),
            )

    for collection in (
        "memory_entries",
        "memory_candidates",
        "profile_items",
    ):
        rows = connection.execute(
            "SELECT id, payload FROM records WHERE collection = ?",
            (collection,),
        ).fetchall()
        for record_id, payload_text in rows:
            value = cast(object, json.loads(payload_text))
            transformed = _walk_memory(value, upgrade=upgrade)
            connection.execute(
                "UPDATE records SET payload = ? "
                "WHERE collection = ? AND id = ?",
                (
                    json.dumps(
                        transformed,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    collection,
                    record_id,
                ),
            )

    connection.execute(
        "UPDATE records SET collection = ? WHERE collection = ?",
        (new_collection, old_collection),
    )


def upgrade(connection: sqlite3.Connection) -> None:
    _transform_records(connection, upgrade=True)


def downgrade(connection: sqlite3.Connection) -> None:
    _transform_records(connection, upgrade=False)
