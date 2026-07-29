"""Background memory curator agent."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal, TypeAlias, cast

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
from nuself.memory.repository import MemoryCandidateRepository, MemoryEntryNotFound, MemoryEntryRepository
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
        source_start = max(cursor, visible_start)
        offset = source_start - visible_start
        new_messages = state.messages[offset:]
        if not _has_memory_worthy_signal(new_messages, self._settings.min_quality_chars):
            return MemoryCuratorResult(
                processed_messages=0,
                created=0,
                updated=0,
                ignored=0,
                log_path=self._memory_log_path(),
            )

        source_ref = f"thread:{thread_id}:{source_start}-{visible_end}"
        decision = self._decide_actions(thread_id, state, source_start, new_messages)
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

        created = 0
        updated = 0
        ignored = 0
        for action in decision.actions:
            if action.action == "create":
                outcome = self._create_candidate(action, source_ref)
                if outcome == "create":
                    created += 1
                elif outcome == "update":
                    updated += 1
                else:
                    ignored += 1
            elif action.action == "update":
                if self._update_candidate(action, source_ref):
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
                "processed_messages": len(new_messages),
                "created": created,
                "updated": updated,
                "ignored": ignored,
            },
        )
        return MemoryCuratorResult(
            processed_messages=len(new_messages),
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

    def _create_candidate(self, action: MemoryAction, source_ref: str) -> MemoryActionType:
        observed_at = _source_observed_at(source_ref)
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

    def _update_candidate(self, action: MemoryAction, source_ref: str) -> bool:
        observed_at = _source_observed_at(source_ref)
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
            errors=(ValueError, MemoryEntryNotFound),
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

    def _memory_log_path(self) -> Path:
        return self._paths.logs_dir / "memory.log"


def _render_transcript(messages: list[ThreadMessage]) -> str:
    return "\n".join(f"{message.role}: {message.content}" for message in messages)


def _source_observed_at(source_ref: str) -> str | None:
    return utc_now_iso() if source_ref.startswith("thread:") else None


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
