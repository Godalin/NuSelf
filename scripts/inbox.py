"""Preview or migrate legacy notification records into Inbox and Delivery."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import cast

from nuself.storage.sqlite import validate_nuself_schema


def migrate(database: Path, *, apply: bool) -> tuple[int, int]:
    """Return migrated Inbox/Delivery counts; write only with explicit apply."""

    connection = sqlite3.connect(database)
    try:
        version = validate_nuself_schema(connection)
        if version < 4:
            raise ValueError("Inbox migration requires a compact schema v4+ database")
        rows = connection.execute(
            "SELECT id, payload FROM records "
            "WHERE collection = 'notification_outbox' ORDER BY id"
        ).fetchall()
        inbox_records: list[tuple[str, str]] = []
        delivery_records: list[tuple[str, str]] = []
        for old_id, encoded in rows:
            if not isinstance(old_id, str) or not isinstance(encoded, str):
                raise ValueError("legacy notification record is invalid")
            raw = json.loads(encoded)
            if not isinstance(raw, dict):
                raise ValueError(f"legacy notification {old_id!r} is not an object")
            value = cast(dict[str, object], raw)
            item_id = f"inbox-{old_id}"
            created_at = _string(value, "created_at")
            old_status = value.get("status")
            inbox_status = "dismissed" if old_status == "dismissed" else "pending"
            item: dict[str, object] = {
                "id": item_id,
                "kind": "legacy_notification",
                "source_id": old_id,
                "title": _string(value, "title"),
                "body": _string(value, "body"),
                "status": inbox_status,
                "idempotency_key": f"legacy-{_string(value, 'idempotency_key')}",
                "created_at": created_at,
                "updated_at": value.get("sent_at") or created_at,
                "context": value.get("context", {}),
            }
            if isinstance(value.get("deep_link"), str):
                item["deep_link"] = value["deep_link"]
            inbox_records.append((item_id, _encode(item)))

            adapters = value.get("required_adapters", [])
            results = value.get("deliveries", {})
            if isinstance(adapters, list) and adapters:
                delivery_id = f"delivery-{item_id}"
                status = (
                    "sent" if old_status == "sent"
                    else "failed" if old_status == "failed"
                    else "pending"
                )
                delivery_records.append((delivery_id, _encode({
                    "id": delivery_id,
                    "item_id": item_id,
                    "status": status,
                    "required_adapters": adapters,
                    "results": results,
                    "created_at": created_at,
                    "context": value.get("context", {}),
                })))
        if apply:
            with connection:
                connection.executemany(
                    "INSERT OR IGNORE INTO records(collection, id, payload) "
                    "VALUES ('inbox_items', ?, ?)", inbox_records,
                )
                connection.executemany(
                    "INSERT OR IGNORE INTO records(collection, id, payload) "
                    "VALUES ('delivery_records', ?, ?)", delivery_records,
                )
                connection.execute(
                    "DELETE FROM records WHERE collection = 'notification_outbox'"
                )
        return len(inbox_records), len(delivery_records)
    finally:
        connection.close()


def _string(value: dict[str, object], name: str) -> str:
    field = value.get(name)
    if not isinstance(field, str):
        raise ValueError(f"legacy notification field {name!r} must be a string")
    return field


def _encode(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    inbox_count, delivery_count = migrate(args.database, apply=args.apply)
    mode = "Migrated" if args.apply else "Would migrate"
    print(f"{mode} {inbox_count} Inbox item(s) and {delivery_count} Delivery record(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
