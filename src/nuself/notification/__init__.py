"""Notification outbox and adapters for proactive agent surface."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, cast

OutboxStatus = Literal["pending", "sent", "failed", "dismissed"]


@dataclass(frozen=True)
class OutboxEntry:
    """One notification intent in the outbox."""

    id: str
    title: str
    body: str
    status: OutboxStatus
    idempotency_key: str
    deep_link: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    sent_at: str | None = None
    attempts: int = 0

    def to_wire(self) -> dict[str, object]:
        wire: dict[str, object] = {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "status": self.status,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
            "attempts": self.attempts,
        }
        if self.deep_link is not None:
            wire["deep_link"] = self.deep_link
        if self.sent_at is not None:
            wire["sent_at"] = self.sent_at
        return wire

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "OutboxEntry":
        return cls(
            id=_expect_str(data, "id"),
            title=_expect_str(data, "title"),
            body=_expect_str(data, "body"),
            status=_expect_status(data, "status"),
            idempotency_key=_expect_str(data, "idempotency_key"),
            deep_link=_optional_str(data, "deep_link"),
            created_at=_expect_str(data, "created_at"),
            sent_at=_optional_str(data, "sent_at"),
            attempts=_expect_int(data, "attempts"),
        )


class NotificationAdapter(Protocol):
    """Adapter that delivers one outbox entry to a notification channel."""

    def send(self, entry: OutboxEntry) -> bool:
        """Attempt to deliver the entry. Return True on success."""
        ...


class LogOnlyNotificationAdapter:
    """Write notification intents to a structured log file."""

    def __init__(self, project_root: Path | None = None) -> None:
        from nuself.config import runtime_paths

        paths = runtime_paths(project_root)
        self._project_root = paths.project_root

    def send(self, entry: OutboxEntry) -> bool:
        from nuself.logs import write_log_event

        write_log_event(
            "outbox",
            "outbox_delivered",
            f"{entry.title}: {entry.body}",
            project_root=self._project_root,
            status=entry.status,
            metadata={
                "entry_id": entry.id,
                "idempotency_key": entry.idempotency_key,
                "deep_link": entry.deep_link,
                "attempts": entry.attempts,
            },
        )
        return True


class NotificationOutbox:
    """File-backed notification outbox under private/outbox/."""

    def __init__(self, project_root: Path | None = None) -> None:
        from nuself.config import runtime_paths

        paths = runtime_paths(project_root)
        self._outbox_dir = paths.private_root / "outbox"

    def list(self, status: OutboxStatus | None = None) -> list[OutboxEntry]:
        entries: list[OutboxEntry] = []
        if not self._outbox_dir.exists():
            return entries
        for path in sorted(self._outbox_dir.glob("*.json")):
            entry = self._read_path(path)
            if status is None or entry.status == status:
                entries.append(entry)
        return entries

    def get(self, entry_id: str) -> OutboxEntry:
        path = self._path_for(entry_id)
        if not path.exists():
            raise OutboxEntryNotFound(entry_id)
        return self._read_path(path)

    def add(self, entry: OutboxEntry) -> OutboxEntry:
        """Add an entry if its idempotency key is not already present."""
        if self._idempotency_key_exists(entry.idempotency_key):
            existing = self._find_by_idempotency_key(entry.idempotency_key)
            if existing is not None:
                return existing
        self._write_path(entry)
        return entry

    def mark_sent(self, entry_id: str) -> OutboxEntry:
        entry = self.get(entry_id)
        updated = OutboxEntry(
            id=entry.id,
            title=entry.title,
            body=entry.body,
            status="sent",
            idempotency_key=entry.idempotency_key,
            deep_link=entry.deep_link,
            created_at=entry.created_at,
            sent_at=datetime.now(UTC).isoformat(),
            attempts=entry.attempts + 1,
        )
        self._write_path(updated)
        return updated

    def mark_failed(self, entry_id: str) -> OutboxEntry:
        entry = self.get(entry_id)
        updated = OutboxEntry(
            id=entry.id,
            title=entry.title,
            body=entry.body,
            status="failed",
            idempotency_key=entry.idempotency_key,
            deep_link=entry.deep_link,
            created_at=entry.created_at,
            sent_at=entry.sent_at,
            attempts=entry.attempts + 1,
        )
        self._write_path(updated)
        return updated

    def dismiss(self, entry_id: str) -> OutboxEntry:
        entry = self.get(entry_id)
        updated = OutboxEntry(
            id=entry.id,
            title=entry.title,
            body=entry.body,
            status="dismissed",
            idempotency_key=entry.idempotency_key,
            deep_link=entry.deep_link,
            created_at=entry.created_at,
            sent_at=entry.sent_at,
            attempts=entry.attempts,
        )
        self._write_path(updated)
        return updated

    def clear(self, status: OutboxStatus) -> int:
        """Remove all entries with the given status. Return count removed."""
        removed = 0
        for entry in self.list(status=status):
            path = self._path_for(entry.id)
            if path.exists():
                path.unlink()
                removed += 1
        return removed

    def _idempotency_key_exists(self, key: str) -> bool:
        return self._find_by_idempotency_key(key) is not None

    def _find_by_idempotency_key(self, key: str) -> OutboxEntry | None:
        for entry in self.list():
            if entry.idempotency_key == key:
                return entry
        return None

    def _path_for(self, entry_id: str) -> Path:
        if "/" in entry_id or entry_id in {"", ".", ".."}:
            raise ValueError(f"invalid entry id: {entry_id}")
        return self._outbox_dir / f"{entry_id}.json"

    def _read_path(self, path: Path) -> OutboxEntry:
        import json

        raw: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"outbox file must contain an object: {path}")
        return OutboxEntry.from_wire(cast(dict[str, object], raw))

    def _write_path(self, entry: OutboxEntry) -> None:
        import json

        self._outbox_dir.mkdir(parents=True, exist_ok=True)
        path = self._path_for(entry.id)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_text(json.dumps(entry.to_wire(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_path.replace(path)


class OutboxEntryNotFound(ValueError):
    """Raised when an outbox entry does not exist."""

    def __init__(self, entry_id: str) -> None:
        super().__init__(f"outbox entry not found: {entry_id}")


# --- small helpers ---


def _expect_str(data: dict[str, object], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"field '{field_name}' must be a string")
    return value


def _optional_str(data: dict[str, object], field_name: str) -> str | None:
    value = data.get(field_name)
    return value if isinstance(value, str) else None


def _expect_int(data: dict[str, object], field_name: str) -> int:
    value = data.get(field_name)
    if not isinstance(value, int):
        raise ValueError(f"field '{field_name}' must be an integer")
    return value


def _expect_status(data: dict[str, object], field_name: str) -> OutboxStatus:
    value = _expect_str(data, field_name)
    if value not in {"pending", "sent", "failed", "dismissed"}:
        raise ValueError(f"unsupported outbox status: {value}")
    return cast(OutboxStatus, value)
