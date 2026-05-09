"""Daemon reflection scheduler with cooldowns and quiet hours."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from nuself.agent.chat import ThreadStore
from nuself.config import config_int, runtime_paths
from nuself.notification import LogOnlyNotificationAdapter, NotificationOutbox, OutboxEntry


@dataclass(frozen=True)
class ReflectionSettings:
    """Configuration for the reflection scheduler."""

    interval_seconds: int
    cooldown_seconds: int
    quiet_start_hour: int
    quiet_end_hour: int

    @classmethod
    def from_project(cls, project_root: Path | None = None) -> "ReflectionSettings":
        interval = config_int("NUSELF_REFLECTION_INTERVAL_SECONDS", 3600, project_root)
        cooldown = config_int("NUSELF_REFLECTION_COOLDOWN_SECONDS", 300, project_root)
        quiet_start = config_int("NUSELF_REFLECTION_QUIET_START_HOUR", 22, project_root)
        quiet_end = config_int("NUSELF_REFLECTION_QUIET_END_HOUR", 7, project_root)
        return cls(
            interval_seconds=max(interval, 60),
            cooldown_seconds=max(cooldown, 0),
            quiet_start_hour=max(0, min(quiet_start, 23)),
            quiet_end_hour=max(0, min(quiet_end, 23)),
        )


class ReflectionScheduler:
    """Decides when the daemon should run a self-reflection cycle."""

    def __init__(self, project_root: Path | None = None) -> None:
        paths = runtime_paths(project_root)
        self._project_root = paths.project_root
        self._settings = ReflectionSettings.from_project(project_root)
        self._last_reflection_path = paths.runtime_dir / "last_reflection.json"
        self._outbox = NotificationOutbox(project_root)
        self._adapter = LogOnlyNotificationAdapter(project_root)

    def should_reflect(self, now: datetime | None = None) -> bool:
        """Check if all trigger conditions are satisfied."""
        if now is None:
            now = datetime.now(UTC)
        if self._in_quiet_hours(now):
            return False
        if self._in_cooldown(now):
            return False
        if self._interval_not_elapsed(now):
            return False
        return True

    def reflect(self, now: datetime | None = None) -> bool:
        """Run one reflection cycle if conditions pass."""
        if now is None:
            now = datetime.now(UTC)
        if not self.should_reflect(now):
            return False
        intent = self._create_reflection_intent(now)
        gate = RelevanceGate(self._project_root)
        if not gate.passes(intent.body):
            return False
        self._write_last_reflection(now, intent.body)
        entry = self._outbox.add(intent)
        self._adapter.send(entry)
        return True

    def _in_quiet_hours(self, now: datetime) -> bool:
        current_hour = now.hour
        start = self._settings.quiet_start_hour
        end = self._settings.quiet_end_hour
        if start < end:
            return start <= current_hour < end
        # Wraps around midnight, e.g. 22:00–07:00
        return current_hour >= start or current_hour < end

    def _in_cooldown(self, now: datetime) -> bool:
        last = self._read_last_reflection()
        if last is None:
            return False
        elapsed = (now - last).total_seconds()
        return elapsed < self._settings.cooldown_seconds

    def _interval_not_elapsed(self, now: datetime) -> bool:
        last = self._read_last_reflection()
        if last is None:
            return False
        elapsed = (now - last).total_seconds()
        return elapsed < self._settings.interval_seconds

    def _read_last_reflection(self) -> datetime | None:
        if not self._last_reflection_path.exists():
            return None
        import json
        from typing import cast

        try:
            raw: object = json.loads(self._last_reflection_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(raw, dict):
            return None
        data = cast(dict[str, object], raw)
        ts_raw = data.get("timestamp")
        if not isinstance(ts_raw, str):
            return None
        try:
            return datetime.fromisoformat(ts_raw)
        except ValueError:
            return None

    def _write_last_reflection(self, now: datetime, body: str | None = None) -> None:
        import json

        self._last_reflection_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, object] = {"timestamp": now.isoformat()}
        if body is not None:
            payload["body"] = body
        self._last_reflection_path.write_text(
            json.dumps(payload, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _create_reflection_intent(self, now: datetime) -> OutboxEntry:
        from nuself.notification.deep_link import DeepLink

        thread_id = "reflections"
        deep_link = DeepLink(thread_id=thread_id).to_url()
        body = IdeaCandidateGenerator(self._project_root).generate()
        return OutboxEntry(
            id=f"reflection-{now.strftime('%Y%m%d-%H%M%S')}-{now.microsecond:06d}",
            title="Daemon reflection",
            body=body,
            status="pending",
            idempotency_key=f"reflection-{now.date().isoformat()}",
            deep_link=deep_link,
        )


class RelevanceGate:
    """Filter reflection candidates by novelty and confidence."""

    def __init__(self, project_root: Path | None = None) -> None:
        from nuself.config import runtime_paths

        paths = runtime_paths(project_root)
        self._project_root = paths.project_root
        self._last_reflection_path = paths.runtime_dir / "last_reflection.json"

    def passes(self, candidate: str) -> bool:
        if candidate == _FALLBACK_BODY:
            # Allow fallback only on first reflection (no previous record)
            return not self._last_reflection_path.exists()
        last_body = self._read_last_body()
        if last_body is not None and candidate == last_body:
            return False
        return True

    def _read_last_body(self) -> str | None:
        import json
        from typing import cast

        if not self._last_reflection_path.exists():
            return None
        try:
            raw: object = json.loads(self._last_reflection_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(raw, dict):
            return None
        data = cast(dict[str, object], raw)
        body = data.get("body")
        return body if isinstance(body, str) else None


_FALLBACK_BODY = "Time for a self-reflection cycle."


class IdeaCandidateGenerator:
    """Generate a short reflection prompt from recent thread activity."""

    def __init__(self, project_root: Path | None = None) -> None:
        from nuself.config import runtime_paths

        paths = runtime_paths(project_root)
        self._project_root = paths.project_root

    def generate(self) -> str:
        from nuself.agent.chat import ThreadStore

        store = ThreadStore(self._project_root)
        preview = self._latest_thread_preview(store)
        if preview is not None:
            return f"Consider: {preview}"
        return "Time for a self-reflection cycle."

    def _latest_thread_preview(self, store: ThreadStore) -> str | None:
        for thread_id in reversed(store.list()):
            state = store.load(thread_id)
            for msg in reversed(state.messages):
                if msg.role == "user":
                    return msg.content[:80]
        return None
