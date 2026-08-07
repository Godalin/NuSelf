"""Legacy Notification-to-Inbox migration."""

# pyright: reportPrivateUsage=false

import json
import sqlite3
from pathlib import Path

from scripts.inbox import migrate
from nuself.storage.authority import _create_sqlite_backend


def test_migration_previews_then_moves_legacy_records(tmp_path: Path) -> None:
    database = tmp_path / "nuself.sqlite"
    backend = _create_sqlite_backend(db_path=database)
    backend.close()
    connection = sqlite3.connect(database)
    payload = {
        "id": "notify-reflection-1", "title": "Reflection", "body": "Review it",
        "status": "sent", "idempotency_key": "notify-reflection-1",
        "created_at": "2026-08-03T10:00:00+00:00", "sent_at": "2026-08-03T10:01:00+00:00",
        "required_adapters": ["macos"],
        "deliveries": {"macos": {"status": "sent", "attempts": 1, "sent_at": "2026-08-03T10:01:00+00:00"}},
    }
    connection.execute(
        "INSERT INTO records VALUES (?, ?, ?)",
        ("notification_outbox", payload["id"], json.dumps(payload)),
    )
    connection.commit()
    connection.close()

    assert migrate(database, apply=False) == (1, 1)
    assert migrate(database, apply=True) == (1, 1)

    connection = sqlite3.connect(database)
    try:
        collections = connection.execute(
            "SELECT collection FROM records ORDER BY collection"
        ).fetchall()
    finally:
        connection.close()
    assert collections == [("delivery_records",), ("inbox_items",)]
