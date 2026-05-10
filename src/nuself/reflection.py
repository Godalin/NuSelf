"""Daemon reflection scheduler with cooldowns and quiet hours."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from nuself.agent.chat import ThreadStore
from nuself.config import runtime_paths
from nuself.config_reflection import ReflectionConfig
from nuself.domain.memory import now_iso
from nuself.domain.proactive import IdeaCandidate, RelevanceScore
from nuself.notification import NotificationOutbox, OutboxEntry


@dataclass(frozen=True)
class ReflectionEvent:
    """Event that can trigger an immediate reflection cycle."""

    event_type: str
    payload: dict[str, object]
    created_at: str


class ReflectionScheduler:
    """Decides when the daemon should run a self-reflection cycle."""

    def __init__(self, project_root: Path | None = None, config: ReflectionConfig | None = None) -> None:
        paths = runtime_paths(project_root)
        self._project_root = paths.project_root
        self._config = config or ReflectionConfig.from_yaml(
            project_root / "private" / "reflection_config.yaml" if project_root else None
        )
        self._last_reflection_path = paths.runtime_dir / "last_reflection.json"
        self._outbox = NotificationOutbox(project_root)
        self._event_queue: list[ReflectionEvent] = []

    def trigger_event(self, event: ReflectionEvent) -> None:
        """Queue an event-triggered reflection request."""
        self._event_queue.append(event)

    def should_reflect(self, now: datetime | None = None) -> bool:
        """Check if all trigger conditions are satisfied."""
        if now is None:
            now = datetime.now(UTC)
        if self._in_quiet_hours(now):
            return False
        if self._event_queue:
            return True
        if self._in_cooldown(now):
            return False
        if self._interval_not_elapsed(now):
            return False
        if not self._daily_cap_not_reached(now):
            return False
        return True

    def reflect(self, now: datetime | None = None) -> bool:
        """Run one reflection cycle if conditions pass."""
        if now is None:
            now = datetime.now(UTC)
        if not self.should_reflect(now):
            return False
        # Consume any queued events before generating candidates
        self._event_queue.clear()
        candidates = IdeaCandidateGenerator(self._project_root).generate()
        if not candidates:
            return False
        gate = RelevanceGate(self._project_root)
        best = candidates[0]
        score = gate.score(best)
        if not score.passes:
            return False
        # High-value candidates go through competitive persona discussion
        title = best.title
        body = best.body
        if score.composite >= self._config.persona_discussion_threshold:
            from nuself.proactive_persona import ProactivePersonaDiscussion

            discussion = ProactivePersonaDiscussion(config=self._config)
            result = discussion.discuss(best)
            if not result.approved:
                return False
            title = result.revised_title
            body = result.revised_body
        intent = self._candidate_to_outbox_entry(best, now, title=title, body=body)
        self._write_last_reflection(now, body)
        self._outbox.add(intent)
        return True

    def _in_quiet_hours(self, now: datetime) -> bool:
        current_hour = now.hour
        start = self._config.quiet_start_hour
        end = self._config.quiet_end_hour
        if start < end:
            return start <= current_hour < end
        # Wraps around midnight, e.g. 22:00–07:00
        return current_hour >= start or current_hour < end

    def _in_cooldown(self, now: datetime) -> bool:
        last = self._read_last_reflection()
        if last is None:
            return False
        elapsed = (now - last).total_seconds()
        return elapsed < self._config.cooldown_seconds

    def _interval_not_elapsed(self, now: datetime) -> bool:
        last = self._read_last_reflection()
        if last is None:
            return False
        jittered = self._jittered_interval()
        elapsed = (now - last).total_seconds()
        return elapsed < jittered

    def _jittered_interval(self) -> int:
        import random

        base = self._config.interval_seconds
        jitter = base * self._config.jitter_percent // 100
        if jitter == 0:
            return base
        return base + random.randint(-jitter, jitter)

    def _daily_cap_not_reached(self, now: datetime) -> bool:
        count = self._reflection_count_today(now)
        return count < self._config.daily_cap

    def _reflection_count_today(self, now: datetime) -> int:
        if not self._last_reflection_path.exists():
            return 0
        import json
        from typing import cast

        try:
            raw: object = json.loads(self._last_reflection_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return 0
        if not isinstance(raw, dict):
            return 0
        data = cast(dict[str, object], raw)
        count = data.get("daily_count")
        date = data.get("daily_date")
        if not isinstance(count, int) or not isinstance(date, str):
            return 0
        if date == now.date().isoformat():
            return count
        return 0

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
        count = self._reflection_count_today(now) + 1
        payload: dict[str, object] = {
            "timestamp": now.isoformat(),
            "daily_count": count,
            "daily_date": now.date().isoformat(),
        }
        if body is not None:
            payload["body"] = body
        self._last_reflection_path.write_text(
            json.dumps(payload, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _candidate_to_outbox_entry(
        self,
        candidate: IdeaCandidate,
        now: datetime,
        title: str | None = None,
        body: str | None = None,
    ) -> OutboxEntry:
        from nuself.notification.deep_link import DeepLink

        thread_id = candidate.suggested_thread_id or "reflections"
        deep_link = DeepLink(action="open_thread", thread_id=thread_id).to_url()
        return OutboxEntry(
            id=f"reflection-{now.strftime('%Y%m%d-%H%M%S')}-{now.microsecond:06d}",
            title=title if title is not None else candidate.title,
            body=body if body is not None else candidate.body,
            status="pending",
            idempotency_key=f"reflection-{now.date().isoformat()}",
            deep_link=deep_link,
        )


class RelevanceGate:
    """Multi-dimensional relevance gate for proactive candidates."""

    def __init__(self, project_root: Path | None = None) -> None:
        from nuself.config import runtime_paths

        paths = runtime_paths(project_root)
        self._project_root = paths.project_root
        self._last_reflection_path = paths.runtime_dir / "last_reflection.json"

    def score(self, candidate: IdeaCandidate) -> RelevanceScore:
        novelty = self._score_novelty(candidate)
        confidence = max(0.0, min(1.0, candidate.confidence))
        urgency = max(0.0, min(1.0, candidate.urgency))
        interruption_cost = max(0.0, min(1.0, candidate.interruption_cost))
        cooldown_ok = self._cooldown_ok()

        composite = (
            novelty * 0.25
            + confidence * 0.20
            + urgency * 0.25
            - interruption_cost * 0.15
            + (1.0 if cooldown_ok else 0.0) * 0.15
        )
        composite = max(0.0, min(1.0, composite))

        reasons: list[str] = []
        if novelty < 0.5:
            reasons.append("low_novelty")
        if confidence < 0.5:
            reasons.append("low_confidence")
        if urgency >= 0.7:
            reasons.append("high_urgency")
        if interruption_cost >= 0.7:
            reasons.append("high_interruption_cost")
        if not cooldown_ok:
            reasons.append("cooldown_active")
        if not reasons:
            reasons.append("ok")

        threshold = 0.5
        passes = composite >= threshold and not (interruption_cost >= 0.9 and urgency < 0.5)

        return RelevanceScore(
            passes=passes,
            novelty=novelty,
            confidence=confidence,
            urgency=urgency,
            interruption_cost=interruption_cost,
            cooldown_ok=cooldown_ok,
            composite=composite,
            reasons=tuple(reasons),
        )

    def passes(self, candidate: IdeaCandidate) -> bool:
        return self.score(candidate).passes

    def _score_novelty(self, candidate: IdeaCandidate) -> float:
        if candidate.body == _FALLBACK_BODY:
            return 1.0 if not self._last_reflection_path.exists() else 0.0
        last_body = self._read_last_body()
        if last_body is not None:
            if candidate.body == last_body:
                return 0.0
            if candidate.body in last_body or last_body in candidate.body:
                return 0.3
        return 1.0

    def _cooldown_ok(self) -> bool:
        if not self._last_reflection_path.exists():
            return True
        last = self._read_last_timestamp()
        if last is None:
            return True
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        elapsed = (now - last).total_seconds()
        return elapsed >= 300  # default cooldown 5 minutes

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

    def _read_last_timestamp(self) -> datetime | None:
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
        ts_raw = data.get("timestamp")
        if not isinstance(ts_raw, str):
            return None
        try:
            return datetime.fromisoformat(ts_raw)
        except ValueError:
            return None


_FALLBACK_BODY = "Time for a self-reflection cycle."


class IdeaCandidateGenerator:
    """Generate structured reflection candidates from recent activity."""

    def __init__(self, project_root: Path | None = None) -> None:
        from nuself.config import runtime_paths

        paths = runtime_paths(project_root)
        self._project_root = paths.project_root

    def generate(self, max_candidates: int = 3) -> list[IdeaCandidate]:
        from nuself.agent.chat import ThreadStore

        store = ThreadStore(self._project_root)
        preview = self._latest_thread_preview(store)
        if preview is None:
            return []
        candidate = IdeaCandidate(
            id=f"candidate-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{datetime.now(UTC).microsecond:06d}",
            title="Recent thread reflection",
            body=f"Consider: {preview}",
            candidate_type="question",
            confidence=0.5,
            novelty=0.5,
            urgency=0.3,
            interruption_cost=0.2,
            evidence_refs=(),
            suggested_thread_id=None,
            source_summary="latest user message",
            created_at=now_iso(),
        )
        return [candidate]

    def _latest_thread_preview(self, store: ThreadStore) -> str | None:
        for thread_id in reversed(store.list()):
            state = store.load(thread_id)
            for msg in reversed(state.messages):
                if msg.role == "user":
                    return msg.content[:80]
        return None

    def _recent_thread_context(self, max_threads: int = 5, max_messages: int = 10) -> str:
        from nuself.agent.chat import ThreadStore

        store = ThreadStore(self._project_root)
        lines: list[str] = []
        for thread_id in reversed(store.list()[-max_threads:]):
            state = store.load(thread_id)
            lines.append(f"Thread {thread_id}:")
            for msg in state.messages[-max_messages:]:
                lines.append(f"  {msg.role}: {msg.content[:120]}")
        return "\n".join(lines)

    def _recent_memory_context(self, max_entries: int = 8) -> str:
        from nuself.memory.repository import MemoryEntryRepository

        repo = MemoryEntryRepository(self._project_root)
        lines: list[str] = []
        for entry in repo.list()[-max_entries:]:
            lines.append(f"- [{entry.type}] {entry.title}: {entry.body[:120]}")
        return "\n".join(lines)

    def _new_source_context(self, max_sources: int = 5) -> str:
        from nuself.memory.source_repository import SourceRepository

        repo = SourceRepository(self._project_root)
        lines: list[str] = []
        for doc in repo.list_documents()[-max_sources:]:
            lines.append(f"- {doc.title or doc.id}")
        return "\n".join(lines)
