"""Background memory curator agent."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal, TypeAlias, cast
from uuid import NAMESPACE_URL, uuid5

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from nuself.agent.chat import ThreadMessage, ThreadState, ThreadStore
from nuself.agent.errors import AgentError
from nuself.agent.structured import StructuredAgent, default_structured_agent
from nuself.clock import utc_now_iso
from nuself.config import runtime_paths
from nuself.domain.memory import MemoryCandidate, MemoryEntry, MemoryEntryType, MemoryEvidence, MemoryObject, MemoryTypeRegistry, default_memory_type_registry
from nuself.memory.audit import (
    run_memory_observed,
    write_curator_audit,
)
from nuself.memory.repository import (
    MemoryCandidateNotFound,
    MemoryCandidateRepository,
    MemoryEntryNotFound,
    MemoryEntryRepository,
)
from nuself.memory.text import looks_like_raw_transcript
from nuself.profile.repository import ProfileItemRepository
from nuself.runtime.observability import report_corrupt_record
from nuself.storage import write_json_atomic
from nuself.trace.service import TraceRecorder

MemoryActionType: TypeAlias = Literal["create", "update", "ignore"]
DecisionStatus: TypeAlias = Literal["ready", "deferred"]


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


@dataclass(frozen=True)
class MemoryAction:
    """One structured action proposed by the memory curator agent."""

    action: MemoryActionType
    title: str
    body: str
    type: MemoryEntryType = "episode"
    tags: tuple[str, ...] = ()
    entry_id: str | None = None
    confidence: float = 0.6
    reason: str = ""


@dataclass(frozen=True)
class MemoryDecision:
    """Structured decision returned by the curator agent."""

    status: DecisionStatus
    actions: tuple[MemoryAction, ...] = ()
    reason: str = ""


class CuratorActionItem(BaseModel):
    """One structured memory curation action from the LLM."""

    model_config = ConfigDict(strict=True, extra="forbid")

    action: Literal["create", "update", "ignore"] = Field(description="Memory action type.")
    title: str = Field(default="", description="Memory entry title.")
    body: str = Field(default="", description="Memory entry body.")
    type: str = Field(default="episode", description="Memory entry type.")
    tags: list[str] = Field(
        default_factory=lambda: list[str](),
        max_length=4,
        description="One to four short tags.",
    )
    entry_id: str | None = Field(default=None, description="Existing entry id to update.")
    confidence: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Confidence from 0.0 to 1.0.",
    )
    reason: str = Field(default="", description="Reason for the action.")


class CuratorActionsOutput(BaseModel):
    """Structured curator actions response from the LLM."""

    model_config = ConfigDict(strict=True, extra="forbid")

    actions: list[CuratorActionItem] = Field(description="Memory curation actions.")


@dataclass(frozen=True)
class MemoryCuratorPlan:
    """One durable structured decision awaiting cursor completion."""

    thread_id: str
    source_start: int
    source_end: int
    observed_at: str
    actions: tuple[MemoryAction, ...]

    @property
    def source_ref(self) -> str:
        return (
            f"thread:{self.thread_id}:{self.source_start}-{self.source_end}"
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "thread_id": self.thread_id,
            "source_start": self.source_start,
            "source_end": self.source_end,
            "observed_at": self.observed_at,
            "actions": [
                {
                    "action": action.action,
                    "title": action.title,
                    "body": action.body,
                    "type": action.type,
                    "tags": list(action.tags),
                    "entry_id": action.entry_id,
                    "confidence": action.confidence,
                    "reason": action.reason,
                }
                for action in self.actions
            ],
        }

    @classmethod
    def from_wire(
        cls,
        data: dict[str, object],
        *,
        expected_thread_id: str,
        allowed_types: tuple[str, ...],
    ) -> MemoryCuratorPlan:
        expected_fields = {
            "thread_id",
            "source_start",
            "source_end",
            "observed_at",
            "actions",
        }
        if set(data) != expected_fields:
            raise ValueError("curator plan fields differ from schema")
        thread_id = data["thread_id"]
        if thread_id != expected_thread_id:
            raise ValueError("curator plan thread identity mismatch")
        source_start = data["source_start"]
        source_end = data["source_end"]
        observed_at = data["observed_at"]
        if (
            isinstance(source_start, bool)
            or not isinstance(source_start, int)
            or isinstance(source_end, bool)
            or not isinstance(source_end, int)
            or source_start < 0
            or source_end <= source_start
        ):
            raise ValueError("curator plan source range is invalid")
        if not isinstance(observed_at, str) or observed_at == "":
            raise ValueError("curator plan observed_at is invalid")
        raw_actions = data["actions"]
        if not isinstance(raw_actions, list) or not raw_actions:
            raise ValueError("curator plan actions must be a non-empty list")
        action_values = cast(list[object], raw_actions)
        actions = tuple(
            _action_from_item(
                CuratorActionItem.model_validate(raw_action),
                allowed_types=allowed_types,
            )
            for raw_action in action_values
        )
        return cls(
            thread_id=expected_thread_id,
            source_start=source_start,
            source_end=source_end,
            observed_at=observed_at,
            actions=actions,
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
    ) -> None:
        paths = runtime_paths(project_root)
        self._paths = paths
        self._agent = agent or default_structured_agent(
            CuratorActionsOutput,
            project_root=paths.project_root,
            component="memory",
        )
        self._settings = settings or MemoryCuratorSettings()
        self._thread_store = thread_store or ThreadStore(paths.project_root)
        self._repository = repository or MemoryEntryRepository(paths.project_root)
        self._profile_repository = profile_repository or ProfileItemRepository(paths.project_root)
        self._candidate_repository = candidate_repository or MemoryCandidateRepository(
            paths.project_root,
            entry_repository=self._repository,
        )
        self._registry = registry or default_memory_type_registry()
        self._trace_recorder = trace_recorder
        self._source_trace_id: str | None = None

    def run_once(self, thread_id: str = "default", *, source_trace_id: str | None = None) -> MemoryCuratorResult:
        self._source_trace_id = source_trace_id
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
            self._save_plan(plan)
        source_start = plan.source_start
        visible_end = plan.source_end
        source_ref = plan.source_ref
        processed_messages = visible_end - source_start

        created = 0
        updated = 0
        ignored = 0
        for action_index, action in enumerate(plan.actions):
            candidate_id = _curator_candidate_id(
                source_ref,
                action_index,
            )
            if action.action == "create":
                outcome = self._create_candidate(
                    action,
                    source_ref,
                    candidate_id=candidate_id,
                    observed_at=plan.observed_at,
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
    ) -> MemoryActionType:
        staged = self._staged_candidate(
            candidate_id,
            source_ref=source_ref,
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
                self._auto_accept(candidate)
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
        self._auto_accept(candidate)
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
    ) -> bool:
        if self._staged_candidate(
            candidate_id,
            source_ref=source_ref,
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
        self._auto_accept(candidate)
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
            self._auto_accept(candidate)
        return candidate

    def _auto_accept(self, candidate: MemoryCandidate) -> None:
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
            )

    def _record_memory_update_trace(
        self,
        entry: MemoryEntry,
        *,
        action: str,
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
                source_trace_id=self._source_trace_id,
            ),
            event="trace_recording_failed",
            project_root=self._paths.project_root,
            metadata={
                "memory_id": entry.id,
                "action": action,
            },
        )

    def _load_cursor(self, thread_id: str) -> int:
        path = self._cursor_path(thread_id)
        try:
            raw: object = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("cursor record must be a JSON object")
            cursor = MemoryCuratorCursor.from_wire(
                cast(dict[str, object], raw),
                expected_thread_id=thread_id,
            )
        except FileNotFoundError:
            return 0
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
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
        path = self._plan_path(thread_id)
        try:
            raw: object = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("curator plan record must be a JSON object")
            raw_mapping = cast(dict[str, object], raw)
            stored_thread_id = raw_mapping.get("thread_id")
            stored_source_end = raw_mapping.get("source_end")
            if (
                stored_thread_id == thread_id
                and not isinstance(stored_source_end, bool)
                and isinstance(stored_source_end, int)
                and stored_source_end <= cursor
            ):
                return None
            plan = MemoryCuratorPlan.from_wire(
                raw_mapping,
                expected_thread_id=thread_id,
                allowed_types=self._registry.names(),
            )
            if plan.source_start != cursor:
                raise ValueError(
                    "curator plan does not start at the durable cursor"
                )
            if plan.source_end > next_message_index:
                raise ValueError(
                    "curator plan extends beyond the current thread"
                )
            return plan
        except FileNotFoundError:
            return None
        except (
            json.JSONDecodeError,
            UnicodeDecodeError,
            TypeError,
            ValueError,
        ) as exc:
            report_corrupt_record(
                exc,
                component="memory",
                collection="memory_curator_plans",
                record_id=thread_id,
                project_root=self._paths.project_root,
            )
            raise ValueError(
                f"invalid memory curator plan for thread {thread_id!r}"
            ) from exc

    def _save_plan(self, plan: MemoryCuratorPlan) -> None:
        write_json_atomic(
            self._plan_path(plan.thread_id),
            plan.to_wire(),
        )

    def _save_cursor(self, thread_id: str, processed_message_count: int) -> None:
        path = self._cursor_path(thread_id)
        cursor = MemoryCuratorCursor(
            thread_id=thread_id,
            processed_message_count=processed_message_count,
        )
        write_json_atomic(path, cursor.to_wire())

    def _cursor_path(self, thread_id: str) -> Path:
        if thread_id == "" or "/" in thread_id or thread_id in {".", ".."}:
            raise ValueError(f"invalid thread id: {thread_id}")
        return self._paths.private_root / "memory" / "cursors" / f"{thread_id}.json"

    def _plan_path(self, thread_id: str) -> Path:
        self._cursor_path(thread_id)
        return (
            self._paths.private_root
            / "memory"
            / "plans"
            / f"{thread_id}.json"
        )

    def _memory_log_path(self) -> Path:
        return self._paths.logs_dir / "memory.log"


def _render_transcript(messages: list[ThreadMessage]) -> str:
    return "\n".join(f"{message.role}: {message.content}" for message in messages)


def _curator_candidate_id(source_ref: str, action_index: int) -> str:
    return f"cand_{uuid5(NAMESPACE_URL, f'{source_ref}:{action_index}').hex}"


def _has_memory_worthy_signal(messages: list[ThreadMessage], min_quality_chars: int) -> bool:
    user_text = "\n".join(message.content for message in messages if message.role == "user")
    if len(user_text.strip()) >= min_quality_chars:
        return True
    normalized = user_text.casefold()
    durable_markers = {
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
    }
    return any(marker in normalized for marker in durable_markers)


def _actions_from_output(
    output: CuratorActionsOutput,
    *,
    allowed_types: tuple[str, ...] | None = None,
) -> list[MemoryAction]:
    return [
        _action_from_item(item, allowed_types=allowed_types)
        for item in output.actions
    ]


def _action_from_item(
    item: CuratorActionItem,
    *,
    allowed_types: tuple[str, ...] | None = None,
) -> MemoryAction:
    title = item.title.strip()
    body = item.body.strip()
    if item.action != "ignore" and (title == "" or body == ""):
        raise ValueError("memory mutation action requires title and body")
    tags = _normalize_tags(item.tags)
    if item.action != "ignore" and not tags:
        raise ValueError("memory mutation action requires tags")
    if item.action != "ignore" and _looks_like_raw_transcript(body):
        raise ValueError("memory mutation action body must not be a transcript")
    if item.action == "update" and (
        item.entry_id is None or item.entry_id.strip() == ""
    ):
        raise ValueError("memory update action requires entry_id")
    memory_type = _memory_type(item.type, allowed_types=allowed_types)
    return MemoryAction(
        action=item.action,
        type=memory_type,
        title=title,
        body=body,
        tags=tags,
        entry_id=item.entry_id,
        confidence=item.confidence,
        reason=item.reason,
    )


def _memory_type(value: str, *, allowed_types: tuple[str, ...] | None = None) -> MemoryEntryType:
    names = allowed_types or default_memory_type_registry().names()
    if value in names:
        return cast(MemoryEntryType, value)
    raise ValueError(f"unsupported memory type: {value}")


def _normalize_tags(tags: list[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        clean = tag.strip()
        if clean == "" or clean in seen:
            continue
        normalized.append(clean)
        seen.add(clean)
    return tuple(normalized)
def _looks_like_raw_transcript(text: str) -> bool:
    return looks_like_raw_transcript(text)
