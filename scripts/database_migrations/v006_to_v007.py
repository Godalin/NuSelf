"""Schema v6↔v7: replace conversation-backed curation with observations."""

from __future__ import annotations

import json
import sqlite3
from typing import cast
from uuid import NAMESPACE_URL, uuid5


_MIGRATION_TIME = "1970-01-01T00:00:00+00:00"


def _load_records(
    connection: sqlite3.Connection,
    collection: str,
) -> list[tuple[str, dict[str, object]]]:
    result: list[tuple[str, dict[str, object]]] = []
    for record_id, payload in connection.execute(
        "SELECT id, payload FROM records WHERE collection = ?", (collection,)
    ).fetchall():
        value = cast(object, json.loads(payload))
        if not isinstance(record_id, str) or not isinstance(value, dict):
            raise ValueError(f"invalid {collection} record")
        result.append((record_id, cast(dict[str, object], value)))
    return result


def _put(
    connection: sqlite3.Connection,
    collection: str,
    record_id: str,
    payload: dict[str, object],
) -> None:
    stored_payload = {
        key: value for key, value in payload.items() if key != "id"
    }
    existing = connection.execute(
        "SELECT payload FROM records WHERE collection = ? AND id = ?",
        (collection, record_id),
    ).fetchone()
    encoded = json.dumps(
        stored_payload, ensure_ascii=False, separators=(",", ":")
    )
    if existing is not None:
        if len(existing) != 1 or existing[0] != encoded:
            raise ValueError(f"{collection} identity collision: {record_id}")
        return
    connection.execute(
        "INSERT INTO records(collection, id, payload) VALUES (?, ?, ?)",
        (
            collection,
            record_id,
            encoded,
        ),
    )


def _source_ref(conversation_id: str, start: int, end: int) -> str:
    identity = f"{conversation_id}:{start}-{end}"
    return f"interaction:{uuid5(NAMESPACE_URL, identity).hex}"


def _observation_id(source_ref: str) -> str:
    return f"obs_{uuid5(NAMESPACE_URL, source_ref).hex}"


def _fragments(
    state: dict[str, object], start: int, end: int
) -> list[str]:
    visible_start = state.get("message_start_index", 0)
    messages = state.get("messages")
    if type(visible_start) is not int or not isinstance(messages, list):
        raise ValueError("invalid conversation range during v7 migration")
    result: list[str] = []
    for item in cast(list[object], messages)[start - visible_start : end - visible_start]:
        if not isinstance(item, dict):
            raise ValueError("invalid conversation message during v7 migration")
        message = cast(dict[str, object], item)
        role = message.get("role")
        content = message.get("content")
        if not isinstance(role, str) or not isinstance(content, str):
            raise ValueError("invalid conversation message during v7 migration")
        result.append(f"{role}: {content}")
    return result


def _publish_range(
    connection: sqlite3.Connection,
    *,
    conversation_id: str,
    state: dict[str, object],
    start: int,
    end: int,
) -> tuple[str, str] | None:
    if end <= start:
        return None
    source_ref = _source_ref(conversation_id, start, end)
    observation_id = _observation_id(source_ref)
    fragments = _fragments(state, start, end)
    if not fragments:
        return None
    _put(
        connection,
        "memory_observations",
        observation_id,
        {
            "id": observation_id,
            "source_ref": source_ref,
            "fragments": fragments,
            "observed_at": _MIGRATION_TIME,
            "status": "pending",
            "source_trace_id": None,
        },
    )
    return observation_id, source_ref


def _rewrite_evidence(value: object, *, upgrade: bool) -> object:
    if isinstance(value, dict):
        record = cast(dict[str, object], value)
        transformed: dict[str, object] = {}
        for key, item in record.items():
            if key == "source_type" and item == ("conversation" if upgrade else "observation"):
                transformed[key] = "observation" if upgrade else "conversation"
            elif upgrade and key == "source_ref" and isinstance(item, str):
                transformed[key] = _anonymize_legacy_ref(item)
            elif upgrade and key == "source_refs" and isinstance(item, list):
                transformed[key] = [
                    _anonymize_legacy_ref(ref) if isinstance(ref, str) else ref
                    for ref in cast(list[object], item)
                ]
            else:
                transformed[key] = _rewrite_evidence(item, upgrade=upgrade)
        return transformed
    if isinstance(value, list):
        return [_rewrite_evidence(item, upgrade=upgrade) for item in cast(list[object], value)]
    return value


def _anonymize_legacy_ref(value: str) -> str:
    if not value.startswith("conversation:"):
        return value
    identity = value.removeprefix("conversation:")
    return f"interaction:{uuid5(NAMESPACE_URL, identity).hex}"


def upgrade(connection: sqlite3.Connection) -> None:
    held_plans = _load_records(connection, "memory_observation_plans")
    cursors = {
        record_id: record.get("processed_message_count", 0)
        for record_id, record in _load_records(connection, "memory_curator_cursors")
    }
    plans = dict(_load_records(connection, "memory_curator_plans"))
    for conversation_id, state in _load_records(connection, "conversations"):
        visible_start = state.get("message_start_index", 0)
        visible_end = state.get("next_message_index")
        cursor = cursors.get(conversation_id, 0)
        if type(visible_start) is not int or type(visible_end) is not int or type(cursor) is not int:
            raise ValueError("invalid conversation cursor during v7 migration")
        start = max(visible_start, cursor)
        plan = plans.get(conversation_id)
        if plan is not None:
            plan_start = plan.get("source_start")
            plan_end = plan.get("source_end")
            actions = plan.get("actions")
            observed_at = plan.get("observed_at")
            if type(plan_start) is not int or type(plan_end) is not int or not isinstance(actions, list) or not isinstance(observed_at, str):
                raise ValueError("invalid curator plan during v7 migration")
            published = _publish_range(
                connection,
                conversation_id=conversation_id,
                state=state,
                start=max(start, plan_start),
                end=plan_end,
            )
            if published is not None:
                observation_id, source_ref = published
                connection.execute(
                    "UPDATE records SET id = ?, payload = ? WHERE collection = 'memory_curator_plans' AND id = ?",
                    (
                        observation_id,
                        json.dumps(
                            {
                                "observation_id": observation_id,
                                "source_ref": source_ref,
                                "observed_at": observed_at,
                                "actions": actions,
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        conversation_id,
                    ),
                )
            start = max(start, plan_end)
        _publish_range(
            connection,
            conversation_id=conversation_id,
            state=state,
            start=start,
            end=visible_end,
        )
    connection.execute(
        "DELETE FROM records WHERE collection = 'memory_curator_cursors'"
    )
    for collection in ("memory_entries", "memory_candidates", "profile_items"):
        for record_id, record in _load_records(connection, collection):
            transformed = _rewrite_evidence(record, upgrade=True)
            connection.execute(
                "UPDATE records SET payload = ? WHERE collection = ? AND id = ?",
                (json.dumps(transformed, ensure_ascii=False, separators=(",", ":")), collection, record_id),
            )
    for record_id, record in _load_records(connection, "reflection_entries"):
        record.pop("suggested_conversation_id", None)
        connection.execute(
            "UPDATE records SET payload = ? WHERE collection = 'reflection_entries' AND id = ?",
            (json.dumps(record, ensure_ascii=False, separators=(",", ":")), record_id),
        )
    for record_id, record in held_plans:
        _put(connection, "memory_curator_plans", record_id, record)
    connection.execute(
        "DELETE FROM records WHERE collection = 'memory_observation_plans'"
    )


def downgrade(connection: sqlite3.Connection) -> None:
    collision = connection.execute(
        "SELECT 1 FROM records WHERE collection = 'memory_observation_plans' LIMIT 1"
    ).fetchone()
    if collision is not None:
        raise ValueError("memory observation plan holding collection already exists")
    connection.execute(
        "UPDATE records SET collection = 'memory_observation_plans' "
        "WHERE collection = 'memory_curator_plans'"
    )
    for collection in ("memory_entries", "memory_candidates", "profile_items"):
        for record_id, record in _load_records(connection, collection):
            transformed = _rewrite_evidence(record, upgrade=False)
            connection.execute(
                "UPDATE records SET payload = ? WHERE collection = ? AND id = ?",
                (json.dumps(transformed, ensure_ascii=False, separators=(",", ":")), collection, record_id),
            )
