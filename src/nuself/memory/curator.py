"""Background memory curator agent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from langchain_core.messages import HumanMessage, SystemMessage

from nuself.agent.chat import ThreadMessage, ThreadState, ThreadStore
from nuself.agent.errors import AgentError
from nuself.agent.structured import StructuredAgent, default_structured_agent
from nuself.clock import utc_now_iso
from nuself.config import runtime_paths
from nuself.domain.memory import (
    MemoryCandidate,
    MemoryEntry,
    MemoryEvidence,
    MemoryObject,
    MemoryTypeRegistry,
    default_memory_type_registry,
)
from nuself.memory.audit import (
    run_memory_observed,
    write_curator_audit,
)
from nuself.memory.curator_contract import (
    CuratorActionsOutput,
    MemoryAction,
    MemoryActionType,
    MemoryDecision,
    actions_from_output as _actions_from_output,
)
from nuself.memory.curator_plan import (
    MemoryCuratorPlan,
    MemoryCuratorPlanCorruptError,
    MemoryCuratorPlanLockContended,
    MemoryCuratorPlanStore,
    validate_curator_thread_id,
)
from nuself.memory.repository import (
    MemoryCandidateNotFound,
    MemoryCandidateRepository,
    MemoryEntryNotFound,
    MemoryEntryRepository,
)
from nuself.profile.repository import ProfileItemRepository
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.runtime.observability import report_corrupt_record
from nuself.storage import get_default_backend
from nuself.trace.service import TraceRecorder

DURABLE_SIGNAL_MARKERS: tuple[str, ...] = (
    "prefer",
    "remember",
    "important",
    "decide",
    "decision",
    "should",
    "goal",
    "plan",
    "because",
    "why",
    "question",
    "always",
    "never",
    "记住",
    "記住",
    "牢记",
    "牢記",
    "以后",
    "以後",
    "今后",
    "今後",
    "总是",
    "總是",
    "永远",
    "永遠",
    "不要",
    "不再",
    "偏好",
    "喜欢",
    "喜歡",
    "重要",
    "决定",
    "決定",
    "目标",
    "目標",
    "计划",
    "計劃",
    "因为",
    "因為",
    "为什么",
    "為什麼",
    "问题",
    "問題",
    "应该",
    "應該",
    "尽量",
    "儘量",
    "覚えて",
    "記憶して",
    "これから",
    "いつも",
    "常に",
    "二度と",
    "好み",
    "好き",
    "決め",
    "計画",
    "なぜ",
    "質問",
    "べき",
    "ください",
)


@dataclass(frozen=True)
class MemoryCuratorSettings:
    """Policy for one background memory curation run."""

    min_quality_chars: int = 120
    existing_memory_limit: int = 12
    auto_accept: bool = True


@dataclass(frozen=True)
class MemoryCuratorCursor:
    """Authoritative absolute position for one curated thread."""

    thread_id: str
    processed_message_count: int

    @classmethod
    def from_wire(
        cls,
        data: dict[str, object],
        *,
        expected_thread_id: str,
    ) -> MemoryCuratorCursor:
        thread_id = data.get("thread_id")
        if not isinstance(thread_id, str):
            raise ValueError("cursor field 'thread_id' must be a string")
        if thread_id != expected_thread_id:
            raise ValueError(
                "cursor thread identity mismatch: "
                f"expected {expected_thread_id!r}, got {thread_id!r}"
            )
        count = data.get("processed_message_count")
        if isinstance(count, bool) or not isinstance(count, int):
            raise ValueError(
                "cursor field 'processed_message_count' "
                "must be an integer"
            )
        if count < 0:
            raise ValueError(
                "cursor field 'processed_message_count' "
                "must be non-negative"
            )
        return cls(
            thread_id=thread_id,
            processed_message_count=count,
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "thread_id": self.thread_id,
            "processed_message_count": self.processed_message_count,
        }


@dataclass(frozen=True)
class MemoryCuratorResult:
    """Summary of a memory curator run."""

    processed_messages: int
    created: int
    updated: int
    ignored: int
    log_path: Path

    @property
    def changed(self) -> bool:
        return self.created > 0 or self.updated > 0

    def summary(self) -> str:
        return (
            f"processed={self.processed_messages} "
            f"created={self.created} updated={self.updated} ignored={self.ignored}"
        )


class MemoryCurator:

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        agent: StructuredAgent[CuratorActionsOutput] | None = None,
        settings: MemoryCuratorSettings | None = None,
        thread_store: ThreadStore | None = None,
        repository: MemoryEntryRepository | None = None,
        candidate_repository: MemoryCandidateRepository | None = None,
        profile_repository: ProfileItemRepository | None = None,
        registry: MemoryTypeRegistry | None = None,
        trace_recorder: TraceRecorder | None = None,
        plan_store: MemoryCuratorPlanStore | None = None,
    ) -> None:
        paths = runtime_paths(project_root)
        self._paths = paths
        self._agent = agent or default_structured_agent(
            CuratorActionsOutput,
            project_root=paths.project_root,
            component="memory",
        )
        self._settings = settings or MemoryCuratorSettings()
        self._backend = get_default_backend(paths.project_root)
        self._cursor_collection = self._backend.collection(
            "memory_curator_cursors"
        )
        self._thread_store = thread_store or ThreadStore(paths.project_root)
        self._repository = repository or MemoryEntryRepository(
            paths,
            backend=self._backend,
        )
        self._profile_repository = (
            profile_repository
            or ProfileItemRepository(paths, backend=self._backend)
        )
        self._candidate_repository = candidate_repository or MemoryCandidateRepository(
            paths,
            backend=self._backend,
            entry_repository=self._repository,
            profile_repository=self._profile_repository,
        )
        self._registry = registry or default_memory_type_registry()
        self._plan_store = plan_store or MemoryCuratorPlanStore(
            paths,
            self._backend,
            registry=self._registry,
        )
        self._trace_recorder = trace_recorder

    def run_once(
        self,
        thread_id: str = "default",
        *,
        source_trace_id: str | None = None,
    ) -> MemoryCuratorResult:
        try:
            with self._plan_store.exclusive(thread_id):
                return self._run_once_locked(
                    thread_id,
                    source_trace_id=source_trace_id,
                )
        except MemoryCuratorPlanLockContended:
            write_curator_audit(
                "curator_contended",
                "Memory curator found the source thread busy",
                project_root=self._paths.project_root,
                metadata={"thread_id": thread_id},
            )
            return MemoryCuratorResult(
                processed_messages=0,
                created=0,
                updated=0,
                ignored=0,
                log_path=self._memory_log_path(),
            )

    def _run_once_locked(
        self,
        thread_id: str,
        *,
        source_trace_id: str | None,
    ) -> MemoryCuratorResult:
        state = self._thread_store.load(thread_id)
        cursor = self._load_cursor(thread_id)
        visible_start = state.message_start_index
        visible_end = state.next_message_index
        if cursor >= visible_end:
            return MemoryCuratorResult(
                processed_messages=0,
                created=0,
                updated=0,
                ignored=0,
                log_path=self._memory_log_path(),
            )
        plan = self._load_plan(
            thread_id,
            cursor=cursor,
            next_message_index=visible_end,
        )
        if cursor < visible_start:
            write_curator_audit(
                "curator_history_gap",
                "Older unprocessed turns were already compressed",
                project_root=self._paths.project_root,
                metadata={
                    "thread_id": thread_id,
                    "cursor": cursor,
                    "visible_start": visible_start,
                },
            )
        if plan is None:
            source_start = max(cursor, visible_start)
            offset = source_start - visible_start
            new_messages = state.messages[offset:]
            if not _has_memory_worthy_signal(
                new_messages,
                self._settings.min_quality_chars,
            ):
                return MemoryCuratorResult(
                    processed_messages=0,
                    created=0,
                    updated=0,
                    ignored=0,
                    log_path=self._memory_log_path(),
                )

            decision = self._decide_actions(
                thread_id,
                state,
                source_start,
                new_messages,
            )
            source_ref = (
                f"thread:{thread_id}:{source_start}-{visible_end}"
            )
            if decision.status == "deferred":
                write_curator_audit(
                    "curator_deferred",
                    "Memory curator deferred the source range",
                    project_root=self._paths.project_root,
                    metadata={
                        "thread_id": thread_id,
                        "source_ref": source_ref,
                        "processed_messages": 0,
                    },
                )
                return MemoryCuratorResult(
                    processed_messages=0,
                    created=0,
                    updated=0,
                    ignored=0,
                    log_path=self._memory_log_path(),
                )
            plan = MemoryCuratorPlan(
                thread_id=thread_id,
                source_start=source_start,
                source_end=visible_end,
                observed_at=utc_now_iso(),
                actions=decision.actions,
            )
            self._plan_store.save(plan)
        source_start = plan.source_start
        visible_end = plan.source_end
        source_ref = plan.source_ref
        processed_messages = visible_end - source_start

        created = 0
        updated = 0
        ignored = 0
        for action_index, action in enumerate(plan.actions):
            candidate_id = plan.candidate_id(action_index)
            if action.action == "create":
                outcome = self._create_candidate(
                    action,
                    source_ref,
                    candidate_id=candidate_id,
                    observed_at=plan.observed_at,
                    source_trace_id=source_trace_id,
                )
                if outcome == "create":
                    created += 1
                elif outcome == "update":
                    updated += 1
                else:
                    ignored += 1
            elif action.action == "update":
                if self._update_candidate(
                    action,
                    source_ref,
                    candidate_id=candidate_id,
                    observed_at=plan.observed_at,
                    source_trace_id=source_trace_id,
                ):
                    updated += 1
                else:
                    ignored += 1
            else:
                ignored += 1
        self._save_cursor(thread_id, visible_end)
        write_curator_audit(
            "curator_completed",
            "Memory curator processed a source range",
            project_root=self._paths.project_root,
            metadata={
                "thread_id": thread_id,
                "source_ref": source_ref,
                "processed_messages": processed_messages,
                "created": created,
                "updated": updated,
                "ignored": ignored,
            },
        )
        return MemoryCuratorResult(
            processed_messages=processed_messages,
            created=created,
            updated=updated,
            ignored=ignored,
            log_path=self._memory_log_path(),
        )

    def _decide_actions(
        self,
        thread_id: str,
        state: ThreadState,
        cursor: int,
        messages: list[ThreadMessage],
    ) -> MemoryDecision:
        prompt = [
            SystemMessage(
                content=(
                    "You are the NuSelf Memory Curator Agent. Decide whether new working-memory turns "
                    "should create, update, or ignore long-term memory. "
                    "Be conservative. Ignore trivial greetings, name pings, acknowledgements, and idle small talk. "
                    "Prefer updating or refining an existing memory when the meaning is already represented. "
                    "Create only when the discussion contains a durable preference, goal, concept, decision, "
                    "open question, important episode, or instruction. Never copy raw chat transcripts into memory bodies; "
                    "Every create/update action must include one to four short tags. "
                    "Write compressed summaries with evidence-aware wording. Consider existing profile items before "
                    "creating new profile facts or overlapping durable memories. Allowed actions are create, update, ignore. "
                    f"Allowed memory types are {', '.join(self._registry.names())}."
                ),
            ),
            HumanMessage(
                content=(
                    f"Thread: {thread_id}\n"
                    f"Existing summary:\n{state.summary or '(none)'}\n\n"
                    f"Existing memories:\n{self._existing_memory_context() or '(none)'}\n\n"
                    f"Existing profile items:\n{self._existing_profile_context() or '(none)'}\n\n"
                    f"New turns {cursor}-{cursor + len(messages)}:\n{_render_transcript(messages)}\n\n"
                    "Return the required structured action batch. For "
                    "low-value chat, choose one ignore action and explain why."
                ),
            ),
        ]
        try:
            output = self._agent.invoke(prompt)
        except AgentError:
            return MemoryDecision(
                status="deferred",
                reason=(
                    "curator agent unavailable or returned invalid "
                    "structured output"
                ),
            )
        try:
            actions = _actions_from_output(
                output,
                allowed_types=self._registry.names(),
            )
        except ValueError:
            return MemoryDecision(
                status="deferred",
                reason=(
                    "curator agent unavailable or returned invalid "
                    "structured output"
                ),
            )
        if actions:
            return MemoryDecision(status="ready", actions=tuple(actions))
        return MemoryDecision(status="deferred", reason="curator agent returned no valid actions")

    def _existing_memory_context(self) -> str:
        lines: list[str] = []
        for entry in self._repository.list()[: self._settings.existing_memory_limit]:
            tags = f" tags={','.join(entry.tags)}" if entry.tags else ""
            lines.append(f"- id={entry.id} type={entry.type} title={entry.title}{tags}: {entry.body}")
        return "\n".join(lines)

    def _existing_profile_context(self) -> str:
        lines: list[str] = []
        for item in self._profile_repository.list()[: self._settings.existing_memory_limit]:
            tags = f" tags={','.join(item.tags)}" if item.tags else ""
            sources = f" sources={','.join(item.source_refs)}" if item.source_refs else ""
            lines.append(f"- id={item.id} type={item.type} title={item.title}{tags}{sources}: {item.body}")
        return "\n".join(lines)

    def _create_candidate(
        self,
        action: MemoryAction,
        source_ref: str,
        *,
        candidate_id: str,
        observed_at: str,
        source_trace_id: str | None,
    ) -> MemoryActionType:
        staged = self._staged_candidate(
            candidate_id,
            source_ref=source_ref,
            source_trace_id=source_trace_id,
        )
        if staged is not None:
            return (
                "update"
                if staged.action in {"update", "merge"}
                else "create"
            )
        incoming = MemoryObject(
            type=action.type,
            payload={"title": action.title, "body": action.body, "tags": list(action.tags)},
            confidence=action.confidence,
        )
        for existing in self._repository.list()[: self._settings.existing_memory_limit]:
            if self._registry.conflicts(existing.to_memory_object(), incoming):
                merged = self._registry.merge(existing.to_memory_object(), incoming)
                candidate = MemoryCandidate(
                    action="update",
                    type=existing.type,
                    title=cast(str, merged.payload.get("title", action.title)),
                    body=cast(str, merged.payload.get("body", action.body)),
                    tags=cast(list[str], merged.payload.get("tags", existing.tags)),
                    source_refs=[source_ref],
                    evidence=[
                        MemoryEvidence(
                            source_type="thread",
                            source_ref=source_ref,
                            summary=action.reason,
                            observed_at=observed_at,
                        )
                    ],
                    confidence=action.confidence,
                    privacy=existing.privacy,
                    reason=action.reason,
                    id=candidate_id,
                    target_entry_id=existing.id,
                    observed_at=existing.observed_at or observed_at,
                    valid_from=existing.valid_from,
                    valid_until=existing.valid_until,
                    temporal_note=existing.temporal_note,
                    relations=existing.relations,
                )
                self._candidate_repository.save(candidate)
                self._auto_accept(
                    candidate,
                    source_trace_id=source_trace_id,
                )
                write_curator_audit(
                    "candidate_merged",
                    "Memory curator created an update candidate by merging",
                    project_root=self._paths.project_root,
                    metadata={
                        "candidate_id": candidate.id,
                        "target_entry_id": existing.id,
                        "memory_type": candidate.type,
                    },
                )
                return "update"
        candidate = MemoryCandidate(
            action="create",
            type=action.type,
            title=action.title,
            body=action.body,
            tags=list(action.tags),
            source_refs=[source_ref],
            evidence=[
                MemoryEvidence(
                    source_type="thread",
                    source_ref=source_ref,
                    summary=action.reason,
                    observed_at=observed_at,
                )
            ],
            confidence=action.confidence,
            reason=action.reason,
            id=candidate_id,
            observed_at=observed_at,
        )
        self._candidate_repository.save(candidate)
        self._auto_accept(
            candidate,
            source_trace_id=source_trace_id,
        )
        write_curator_audit(
            "candidate_created",
            "Memory curator created a candidate",
            project_root=self._paths.project_root,
            metadata={
                "candidate_id": candidate.id,
                "memory_type": candidate.type,
            },
        )
        return "create"

    def _update_candidate(
        self,
        action: MemoryAction,
        source_ref: str,
        *,
        candidate_id: str,
        observed_at: str,
        source_trace_id: str | None,
    ) -> bool:
        if self._staged_candidate(
            candidate_id,
            source_ref=source_ref,
            source_trace_id=source_trace_id,
        ) is not None:
            return True
        if action.entry_id is None:
            return False
        try:
            existing = self._repository.get(action.entry_id)
        except MemoryEntryNotFound:
            return False
        candidate = MemoryCandidate(
            action="update",
            type=existing.type,
            title=action.title or existing.title,
            body=action.body or existing.body,
            tags=list(action.tags),
            source_refs=[source_ref],
            evidence=[
                MemoryEvidence(
                    source_type="thread",
                    source_ref=source_ref,
                    summary=action.reason,
                    observed_at=observed_at,
                )
            ],
            confidence=action.confidence,
            privacy=existing.privacy,
            reason=action.reason,
            id=candidate_id,
            target_entry_id=existing.id,
            observed_at=existing.observed_at or observed_at,
            valid_from=existing.valid_from,
            valid_until=existing.valid_until,
            temporal_note=existing.temporal_note,
            relations=existing.relations,
        )
        self._candidate_repository.save(candidate)
        self._auto_accept(
            candidate,
            source_trace_id=source_trace_id,
        )
        write_curator_audit(
            "candidate_updated",
            "Memory curator created an explicit update candidate",
            project_root=self._paths.project_root,
            metadata={
                "candidate_id": candidate.id,
                "target_entry_id": existing.id,
                "memory_type": candidate.type,
            },
        )
        return True

    def _staged_candidate(
        self,
        candidate_id: str,
        *,
        source_ref: str,
        source_trace_id: str | None,
    ) -> MemoryCandidate | None:
        try:
            candidate = self._candidate_repository.get(candidate_id)
        except MemoryCandidateNotFound:
            return None
        if candidate.source_refs != (source_ref,):
            raise ValueError(
                "curator plan candidate source identity mismatch: "
                f"{candidate_id}"
            )
        if candidate.review_state == "pending":
            self._auto_accept(
                candidate,
                source_trace_id=source_trace_id,
            )
        return candidate

    def _auto_accept(
        self,
        candidate: MemoryCandidate,
        *,
        source_trace_id: str | None,
    ) -> None:
        if not self._settings.auto_accept:
            return
        result = run_memory_observed(
            lambda: self._candidate_repository.accept(
                candidate.id,
                target_review_state="reviewed",
            ),
            event="auto_accept_failed",
            project_root=self._paths.project_root,
            metadata={
                "candidate_id": candidate.id,
                "action": candidate.action,
                "memory_type": candidate.type,
                "target_entry_id": candidate.target_entry_id,
            },
        )
        if (
            isinstance(result, MemoryEntry)
            and result.review_state != "quarantined"
        ):
            self._record_memory_update_trace(
                result,
                action=candidate.action,
                source_trace_id=source_trace_id,
            )

    def _record_memory_update_trace(
        self,
        entry: MemoryEntry,
        *,
        action: str,
        source_trace_id: str | None,
    ) -> None:
        if self._trace_recorder is None:
            return
        recorder = self._trace_recorder
        run_memory_observed(
            lambda: recorder.record_memory_update(
                memory_id=entry.id,
                title=entry.title,
                summary=entry.body,
                memory_type=entry.type,
                action=action,
                confidence=entry.confidence,
                source_trace_id=source_trace_id,
            ),
            event="trace_recording_failed",
            project_root=self._paths.project_root,
            metadata={
                "memory_id": entry.id,
                "action": action,
            },
        )

    def _load_cursor(self, thread_id: str) -> int:
        try:
            validate_curator_thread_id(thread_id)
            raw = self._cursor_collection.get(thread_id)
            if raw is None:
                return 0
            cursor = MemoryCuratorCursor.from_wire(
                {
                    key: value
                    for key, value in raw.items()
                    if key != "id"
                },
                expected_thread_id=thread_id,
            )
        except ValueError as exc:
            report_corrupt_record(
                exc,
                component="memory",
                collection="memory_curator_cursors",
                record_id=thread_id,
                project_root=self._paths.project_root,
            )
            raise ValueError(
                f"invalid memory curator cursor for thread {thread_id!r}"
            ) from exc
        return cursor.processed_message_count

    def _load_plan(
        self,
        thread_id: str,
        *,
        cursor: int,
        next_message_index: int,
    ) -> MemoryCuratorPlan | None:
        try:
            return self._plan_store.resumable(
                thread_id,
                cursor=cursor,
                next_message_index=next_message_index,
            )
        except MemoryCuratorPlanCorruptError as exc:
            raise ValueError(
                diagnostic_exception_message(exc)
            ) from exc

    def _save_cursor(self, thread_id: str, processed_message_count: int) -> None:
        cursor = MemoryCuratorCursor(
            thread_id=thread_id,
            processed_message_count=processed_message_count,
        )
        validate_curator_thread_id(thread_id)
        self._cursor_collection.put(thread_id, cursor.to_wire())

    def _memory_log_path(self) -> Path:
        return self._paths.logs_dir / "memory.log"


def _render_transcript(messages: list[ThreadMessage]) -> str:
    return "\n".join(f"{message.role}: {message.content}" for message in messages)


def _has_memory_worthy_signal(messages: list[ThreadMessage], min_quality_chars: int) -> bool:
    user_text = "\n".join(message.content for message in messages if message.role == "user")
    if len(user_text.strip()) >= min_quality_chars:
        return True
    normalized = user_text.casefold()
    return any(marker in normalized for marker in DURABLE_SIGNAL_MARKERS)
