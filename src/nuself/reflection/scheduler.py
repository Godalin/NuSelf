"""Daemon reflection scheduler with cooldowns and quiet hours."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from nuself.config import ReflectionSettings
from nuself.domain.proactive import IdeaCandidate, RelevanceScore
from nuself.notification import OutboxEntry
from nuself.notification.deep_link import DeepLink
from nuself.reflection.audit import (
    report_reflection_failure,
    write_reflection_audit,
)
from nuself.reflection.candidates import (
    CandidateListOutput as CandidateListOutput,
)
from nuself.reflection.repository import ReflectionEntry, ReflectionRepository
from nuself.reflection.relevance import (
    RelevanceScoreOutput as RelevanceScoreOutput,
)
from nuself.reflection.schedule_state import (
    REFLECTION_SCHEDULE_STATE_VERSION,
    ReflectionScheduleState,
    ReflectionScheduleStateError,
    read_reflection_schedule_state,
)
from nuself.storage import StorageCollection

_read_schedule_collection = read_reflection_schedule_state


class CandidateGenerator(Protocol):
    def generate(self, max_candidates: int = 3) -> list[IdeaCandidate]: ...


class RelevanceGate(Protocol):
    def score(self, candidate: IdeaCandidate) -> RelevanceScore: ...


class PendingReflectionOrganizer(Protocol):
    def organize_pending(self) -> object: ...


class ReflectionPublisher(Protocol):
    def add(self, entry: OutboxEntry) -> OutboxEntry: ...


class ReflectionDiscussionResult(Protocol):
    @property
    def approved(self) -> bool: ...

    @property
    def revised_title(self) -> str: ...

    @property
    def revised_body(self) -> str: ...

    @property
    def discussion_trace(self) -> tuple[str, ...]: ...


class ReflectionDiscussion(Protocol):
    def discuss(self, candidate: IdeaCandidate) -> ReflectionDiscussionResult: ...


class ReflectionTraceRecorder(Protocol):
    def record_reflection_created(
        self,
        *,
        reflection_id: str,
        title: str,
        body: str,
        candidate_type: str,
        composite_score: float,
        discussion_approved: bool | None,
        conversation_id: str | None = None,
        decision_points: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> object: ...


class ReflectionScheduler:
    """Decides when the daemon should run a self-reflection cycle."""

    def __init__(
        self,
        project_root: Path,
        config: ReflectionSettings,
        *,
        schedule_collection: StorageCollection,
        repository: ReflectionRepository,
        outbox: ReflectionPublisher,
        trace_recorder: ReflectionTraceRecorder,
        candidate_generator: CandidateGenerator,
        relevance_gate: RelevanceGate,
        organizer: PendingReflectionOrganizer,
        discussion: ReflectionDiscussion,
    ) -> None:
        self._project_root = project_root
        self._config = config
        self._schedule_collection = schedule_collection
        self._reflection_repo = repository
        self._outbox = outbox
        self._trace_recorder = trace_recorder
        self._candidate_generator = candidate_generator
        self._relevance_gate = relevance_gate
        self._organizer = organizer
        self._discussion = discussion
    def should_reflect(self, now: datetime | None = None) -> bool:
        """Return whether deterministic scheduling gates allow a reflection cycle."""
        if now is None:
            now = datetime.now(UTC)
        return self._schedule_block_reason(now) is None

    def reflect(self, now: datetime | None = None) -> bool:
        """Run one reflection cycle if conditions pass."""
        
        if now is None:
            now = datetime.now(UTC)
        
        block_reason = self._schedule_block_reason(now)
        if block_reason is not None:
            write_reflection_audit(
                "schedule_blocked",
                "reflection cycle skipped by schedule limits",
                project_root=self._project_root,
                metadata={"reason": block_reason},
            )
            return False
        
        write_reflection_audit(
            "cycle_started",
            "reflection cycle triggered",
            project_root=self._project_root,
        )

        self._organize_pending_reflections()

        candidates = self._candidate_generator.generate()
        if not candidates:
            return False
        
        best = candidates[0]
        score = self._relevance_gate.score(best)
        if not score.passes:
            write_reflection_audit(
                "cycle_filtered",
                f"best candidate filtered by relevance gate: {best.title}",
                project_root=self._project_root,
                metadata={"reason": "filtered_by_gate", "score": float(score.composite)}
            )
            return False
        
        # High-value candidates go through competitive persona discussion
        title = best.title
        body = best.body
        discussion_approved: bool | None = None
        discussion_trace: tuple[str, ...] = ()
        if score.composite >= self._config.gate.persona_discussion_threshold:
            result = self._discussion.discuss(best)
            discussion_approved = result.approved
            discussion_trace = result.discussion_trace
            if not result.approved:
                write_reflection_audit(
                    "cycle_discussion_rejected",
                    f"persona discussion rejected candidate: {best.title}",
                    project_root=self._project_root,
                    metadata={"reason": "discussion_rejected"}
                )
                return False
            title = result.revised_title
            body = result.revised_body
        
        entry = self._candidate_to_reflection_entry(
            best, now, score, title=title, body=body,
            discussion_approved=discussion_approved,
            discussion_trace=discussion_trace,
        )
        self._reflection_repo.add(entry)
        try:
            decision_points: list[str] = [
                f"Relevance gate passed: composite={score.composite:.2f} threshold={self._config.gate.relevance_threshold}",
                f"Novelty={score.novelty:.2f} confidence={score.confidence:.2f} urgency={score.urgency:.2f}",
            ]
            if discussion_approved is not None:
                decision_points.append(
                    f"Persona discussion threshold met (composite >= {self._config.gate.persona_discussion_threshold})"
                )
                decision_points.append(
                    f"Persona discussion {'approved' if discussion_approved else 'rejected'}"
                )
            else:
                decision_points.append(
                    f"Below persona discussion threshold ({self._config.gate.persona_discussion_threshold}), no discussion triggered"
                )

            self._trace_recorder.record_reflection_created(
                reflection_id=entry.id,
                title=entry.title,
                body=entry.body,
                candidate_type=entry.candidate_type,
                composite_score=entry.composite_score,
                discussion_approved=entry.discussion_approved,
                decision_points=decision_points,
            )
        except Exception as exc:
            report_reflection_failure(
                exc,
                event="trace_recording_failed",
                message="Failed to record trace for persisted reflection",
                project_root=self._project_root,
                metadata={"reflection_id": entry.id},
            )
        self._organize_pending_reflections()
        self._write_last_reflection(now, title=title, body=body)

        if self._config.auto_notify:
            intent = self._candidate_to_notify_entry(entry)
            self._outbox.add(intent)

        write_reflection_audit(
            "cycle_completed",
            f"reflection cycle published: {title}",
            project_root=self._project_root,
            metadata={"reason": "published", "score": float(score.composite), "idea_type": best.candidate_type}
        )
        return True

    def _organize_pending_reflections(self) -> None:

        try:
            self._organizer.organize_pending()
        except Exception as exc:
            report_reflection_failure(
                exc,
                event="organizer_failed",
                message="Reflection organizer failed",
                project_root=self._project_root,
                metadata=None,
            )

    def _in_quiet_hours(self, now: datetime) -> bool:
        current_hour = now.astimezone().hour
        start = self._config.scheduler.quiet_start_hour
        end = self._config.scheduler.quiet_end_hour
        if start == end:
            return False
        if start < end:
            return start <= current_hour < end
        # Wraps around midnight, e.g. 22:00–07:00
        return current_hour >= start or current_hour < end

    def _schedule_block_reason(self, now: datetime) -> str | None:
        if self._in_quiet_hours(now):
            return "quiet_hours"
        try:
            state = _read_schedule_collection(self._schedule_collection)
        except ReflectionScheduleStateError as exc:
            self._report_schedule_state_corrupt(exc)
            return "state_corrupt"
        if not self._daily_cap_not_reached(now, state):
            return "daily_cap"
        if self._in_cooldown(now, state):
            return "cooldown"
        if self._interval_not_elapsed(now, state):
            return "interval"
        return None

    def _in_cooldown(
        self,
        now: datetime,
        state: ReflectionScheduleState | None,
    ) -> bool:
        if state is None:
            return False
        elapsed = (now - state.timestamp).total_seconds()
        return elapsed < self._config.scheduler.cooldown_seconds

    def _interval_not_elapsed(
        self,
        now: datetime,
        state: ReflectionScheduleState | None,
    ) -> bool:
        if state is None:
            return False
        jittered = self._jittered_interval()
        elapsed = (now - state.timestamp).total_seconds()
        return elapsed < jittered

    def _jittered_interval(self) -> int:
        import random

        base = self._config.scheduler.interval_seconds
        jitter = base * self._config.scheduler.jitter_percent // 100
        if jitter == 0:
            return base
        return base + random.randint(-jitter, jitter)

    def _daily_cap_not_reached(
        self,
        now: datetime,
        state: ReflectionScheduleState | None,
    ) -> bool:
        count = self._reflection_count_today(now, state)
        return count < self._config.scheduler.daily_cap

    def _reflection_count_today(
        self,
        now: datetime,
        state: ReflectionScheduleState | None,
    ) -> int:
        if state is None:
            return 0
        if state.daily_date == now.astimezone().date():
            return state.daily_count
        return 0

    def _read_last_reflection(self) -> datetime | None:
        state = _read_schedule_collection(self._schedule_collection)
        return state.timestamp if state is not None else None

    def _write_last_reflection(self, now: datetime, title: str | None = None, body: str | None = None) -> None:
        current = _read_schedule_collection(self._schedule_collection)
        count = self._reflection_count_today(now, current) + 1
        state = ReflectionScheduleState(
            schema_version=REFLECTION_SCHEDULE_STATE_VERSION,
            timestamp=now,
            daily_count=count,
            daily_date=now.astimezone().date(),
            title=title,
            body=body,
        )
        self._schedule_collection.put("reflection", state.to_record())

    def _report_schedule_state_corrupt(
        self,
        exc: ReflectionScheduleStateError,
    ) -> None:
        report_reflection_failure(
            exc,
            event="schedule_state_corrupt",
            message="Reflection schedule state is invalid; scheduling is blocked",
            project_root=self._project_root,
            metadata={"record": "scheduler_state/reflection"},
        )

    def _candidate_to_reflection_entry(
        self,
        candidate: IdeaCandidate,
        now: datetime,
        score: RelevanceScore,
        title: str | None = None,
        body: str | None = None,
        discussion_approved: bool | None = None,
        discussion_trace: tuple[str, ...] = (),
    ) -> ReflectionEntry:

        deep_link = DeepLink.for_new_conversation(
            title=candidate.title,
            message=candidate.body,
            candidate_id=candidate.id,
        ).to_url()
        return ReflectionEntry(
            id=f"reflection-{candidate.id}",
            title=title if title is not None else candidate.title,
            body=body if body is not None else candidate.body,
            candidate_type=candidate.candidate_type,
            confidence=candidate.confidence,
            novelty=candidate.novelty,
            urgency=candidate.urgency,
            interruption_cost=candidate.interruption_cost,
            composite_score=score.composite,
            status="pending",
            discussion_approved=discussion_approved,
            discussion_trace=discussion_trace,
            deep_link=deep_link,
            created_at=now.isoformat(),
            reviewed_at=None,
        )

    def _candidate_to_notify_entry(self, entry: ReflectionEntry) -> OutboxEntry:
        return OutboxEntry(
            id=f"notify-{entry.id}",
            title=f"New reflection: {entry.title}",
            body=f"A new reflection idea is available. View it with: nuself reflection show {entry.id}",
            status="pending",
            idempotency_key=f"notify-{entry.id}",
            deep_link=entry.deep_link,
        )
