"""Background memory curator agent."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal, TypeAlias, cast

from nuself.agent.chat import ThreadMessage, ThreadState, ThreadStore
from nuself.config import ensure_runtime_dirs, runtime_paths
from nuself.domain.memory import MemoryCandidate, MemoryEntry, MemoryEntryType, MemoryEvidence, MemoryObject, MemoryTypeRegistry, default_memory_type_registry, now_iso
from nuself.profile.repository import ProfileItemRepository
from nuself.llm import ChatLLM, ChatMessage, default_llm
from nuself.memory.repository import MemoryCandidateRepository, MemoryEntryNotFound, MemoryEntryRepository

MemoryActionType: TypeAlias = Literal["create", "update", "ignore"]
DecisionStatus: TypeAlias = Literal["ready", "deferred"]


@dataclass(frozen=True)
class MemoryCuratorSettings:
    """Policy for one background memory curation run."""

    min_quality_chars: int = 120
    existing_memory_limit: int = 12
    auto_accept: bool = True


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
    entry_id: str | None = None
    confidence: float = 0.6
    reason: str = ""


@dataclass(frozen=True)
class MemoryDecision:
    """Structured decision returned by the curator agent."""

    status: DecisionStatus
    actions: tuple[MemoryAction, ...] = ()
    reason: str = ""


class MemoryCurator:
    """Summarize new working-memory turns into durable memory entries."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        llm: ChatLLM | None = None,
        settings: MemoryCuratorSettings | None = None,
        thread_store: ThreadStore | None = None,
        repository: MemoryEntryRepository | None = None,
        candidate_repository: MemoryCandidateRepository | None = None,
        profile_repository: ProfileItemRepository | None = None,
        registry: MemoryTypeRegistry | None = None,
    ) -> None:
        paths = runtime_paths(project_root)
        self._paths = paths
        self._llm = llm or default_llm(paths.project_root)
        self._settings = settings or MemoryCuratorSettings()
        self._thread_store = thread_store or ThreadStore(paths.project_root)
        self._repository = repository or MemoryEntryRepository(paths.project_root)
        self._profile_repository = profile_repository or ProfileItemRepository(paths.project_root)
        self._candidate_repository = candidate_repository or MemoryCandidateRepository(
            paths.project_root,
            entry_repository=self._repository,
        )
        self._registry = registry or default_memory_type_registry()

    def run_once(self, thread_id: str = "default") -> MemoryCuratorResult:
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
            self._append_log(
                f"memory_curator_gap thread={thread_id} cursor={cursor} visible_start={visible_start} "
                "older unprocessed turns were already compressed"
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
            self._append_log(
                f"memory_curator_deferred thread={thread_id} source={source_ref} "
                f"processed=0 reason={decision.reason!r}"
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
        self._append_log(
            f"memory_curator thread={thread_id} source={source_ref} "
            f"processed={len(new_messages)} created={created} updated={updated} ignored={ignored}"
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
            ChatMessage(
                role="system",
                content=(
                    "You are the NuSelf Memory Curator Agent. Decide whether new working-memory turns "
                    "should create, update, or ignore long-term memory. Return only JSON with an actions array. "
                    "Be conservative. Ignore trivial greetings, name pings, acknowledgements, and idle small talk. "
                    "Prefer updating or refining an existing memory when the meaning is already represented. "
                    "Create only when the discussion contains a durable preference, goal, concept, decision, "
                    "open question, important episode, or instruction. Never copy raw chat transcripts into memory bodies; "
                    "write compressed summaries with evidence-aware wording. Consider existing profile items before "
                    "creating new profile facts or overlapping durable memories. Allowed actions are create, update, ignore."
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    f"Thread: {thread_id}\n"
                    f"Existing summary:\n{state.summary or '(none)'}\n\n"
                    f"Existing memories:\n{self._existing_memory_context() or '(none)'}\n\n"
                    f"Existing profile items:\n{self._existing_profile_context() or '(none)'}\n\n"
                    f"New turns {cursor}-{cursor + len(messages)}:\n{_render_transcript(messages)}\n\n"
                    "Return JSON like: "
                    '{"actions":[{"action":"create","type":"episode","title":"...","body":"...",'
                    '"confidence":0.7,"reason":"..."}]}\n'
                    "For low-value chat, return: "
                    '{"actions":[{"action":"ignore","reason":"trivial greeting or no durable memory"}]}'
                ),
            ),
        ]
        try:
            raw = self._llm.complete(prompt)
            actions = _parse_actions(raw)
        except (RuntimeError, ValueError):
            return MemoryDecision(status="deferred", reason="curator agent unavailable or returned invalid JSON")
        if actions:
            return MemoryDecision(status="ready", actions=tuple(actions))
        return MemoryDecision(status="deferred", reason="curator agent returned no valid actions")

    def _existing_memory_context(self) -> str:
        lines: list[str] = []
        for entry in self._repository.list()[: self._settings.existing_memory_limit]:
            lines.append(f"- id={entry.id} type={entry.type} title={entry.title}: {entry.body}")
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
            payload={"title": action.title, "body": action.body},
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
                    confidence=_clamp_confidence(action.confidence),
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
                self._append_log(
                    f"merged candidate={candidate.id} target={existing.id} title={candidate.title!r} reason={action.reason!r}"
                )
                return "update"
        candidate = MemoryCandidate(
            action="create",
            type=action.type,
            title=action.title,
            body=action.body,
            source_refs=[source_ref],
            evidence=[
                MemoryEvidence(
                    source_type="thread",
                    source_ref=source_ref,
                    summary=action.reason,
                    observed_at=observed_at,
                )
            ],
            confidence=_clamp_confidence(action.confidence),
            reason=action.reason,
            observed_at=observed_at,
        )
        self._candidate_repository.save(candidate)
        self._auto_accept(candidate)
        self._append_log(
            f"created candidate={candidate.id} type={candidate.type} title={candidate.title!r} reason={action.reason!r}"
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
            tags=existing.tags,
            source_refs=[source_ref],
            evidence=[
                MemoryEvidence(
                    source_type="thread",
                    source_ref=source_ref,
                    summary=action.reason,
                    observed_at=observed_at,
                )
            ],
            confidence=_clamp_confidence(action.confidence),
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
        self._append_log(f"updated candidate={candidate.id} target={existing.id} title={candidate.title!r}")
        return True

    def _auto_accept(self, candidate: MemoryCandidate) -> None:
        if not self._settings.auto_accept:
            return
        try:
            result = self._candidate_repository.accept(candidate.id)
            if isinstance(result, MemoryEntry) and result.review_state != "quarantined":
                reviewed = result.with_updates(review_state="reviewed")
                self._repository.save(reviewed)
        except (ValueError, MemoryEntryNotFound):
            pass

    def _load_cursor(self, thread_id: str) -> int:
        path = self._cursor_path(thread_id)
        try:
            raw: object = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return 0
        if not isinstance(raw, dict):
            return 0
        value = cast(dict[str, object], raw).get("processed_message_count")
        if isinstance(value, int) and value >= 0:
            return value
        return 0

    def _save_cursor(self, thread_id: str, processed_message_count: int) -> None:
        path = self._cursor_path(thread_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"thread_id": thread_id, "processed_message_count": processed_message_count}, indent=2) + "\n",
            encoding="utf-8",
        )

    def _cursor_path(self, thread_id: str) -> Path:
        if thread_id == "" or "/" in thread_id or thread_id in {".", ".."}:
            raise ValueError(f"invalid thread id: {thread_id}")
        return self._paths.private_root / "memory" / "cursors" / f"{thread_id}.json"

    def _memory_log_path(self) -> Path:
        return self._paths.logs_dir / "memory.log"

    def _append_log(self, message: str) -> None:
        ensure_runtime_dirs(self._paths)
        with self._memory_log_path().open("a", encoding="utf-8") as log_file:
            log_file.write(f"{now_iso()} {message}\n")


def _render_transcript(messages: list[ThreadMessage]) -> str:
    return "\n".join(f"{message.role}: {message.content}" for message in messages)


def _source_observed_at(source_ref: str) -> str | None:
    return now_iso() if source_ref.startswith("thread:") else None


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


def _parse_actions(raw: str) -> list[MemoryAction]:
    parsed: object = json.loads(_extract_json_object(raw))
    if not isinstance(parsed, dict):
        return []
    actions_value = cast(dict[str, object], parsed).get("actions")
    if not isinstance(actions_value, list):
        return []
    actions: list[MemoryAction] = []
    for item in cast(list[object], actions_value):
        if not isinstance(item, dict):
            continue
        action = _parse_action(cast(dict[str, object], item))
        if action is not None:
            actions.append(action)
    return actions


def _parse_action(raw: dict[str, object]) -> MemoryAction | None:
    action_value = raw.get("action")
    if action_value not in {"create", "update", "ignore"}:
        return None
    title = _string_field(raw, "title")
    body = _string_field(raw, "body")
    if action_value != "ignore" and (title == "" or body == ""):
        return None
    if action_value != "ignore" and _looks_like_raw_transcript(body):
        return None
    memory_type = _memory_type(raw.get("type"))
    return MemoryAction(
        action=cast(MemoryActionType, action_value),
        type=memory_type,
        title=title,
        body=body,
        entry_id=_optional_string_field(raw, "entry_id"),
        confidence=_number_field(raw, "confidence", 0.6),
        reason=_string_field(raw, "reason"),
    )


def _memory_type(value: object) -> MemoryEntryType:
    if value in {
        "source_note",
        "profile_fact",
        "belief",
        "preference",
        "goal",
        "concept",
        "style_trait",
        "episode",
        "open_question",
        "instruction",
    }:
        return cast(MemoryEntryType, value)
    return "episode"


def _string_field(raw: dict[str, object], field_name: str) -> str:
    value = raw.get(field_name)
    return value if isinstance(value, str) else ""


def _optional_string_field(raw: dict[str, object], field_name: str) -> str | None:
    value = raw.get(field_name)
    return value if isinstance(value, str) and value != "" else None


def _number_field(raw: dict[str, object], field_name: str, default: float) -> float:
    value = raw.get(field_name)
    if isinstance(value, int | float):
        return float(value)
    return default


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(value, 1.0))


def _extract_json_object(raw: str) -> str:
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
        stripped = "\n".join(lines).strip()
    return stripped


def _looks_like_raw_transcript(text: str) -> bool:
    normalized = text.casefold()
    markers = normalized.count("user:") + normalized.count("assistant:")
    return markers >= 2
