"""Background memory curator agent."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal, TypeAlias, cast

from nuself.agent.chat import ThreadMessage, ThreadState, ThreadStore
from nuself.config import ensure_runtime_dirs, runtime_paths
from nuself.domain.memory import MemoryEntry, MemoryEntryType, ReviewState, now_iso
from nuself.llm import ChatLLM, ChatMessage, default_llm
from nuself.memory.repository import MemoryEntryNotFound, MemoryEntryRepository

MemoryActionType: TypeAlias = Literal["create", "update", "ignore"]


@dataclass(frozen=True)
class MemoryCuratorSettings:
    """Policy for one background memory curation run."""

    min_new_messages: int = 2
    existing_memory_limit: int = 12


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
    ) -> None:
        paths = runtime_paths(project_root)
        self._paths = paths
        self._llm = llm or default_llm(paths.project_root)
        self._settings = settings or MemoryCuratorSettings()
        self._thread_store = thread_store or ThreadStore(paths.project_root)
        self._repository = repository or MemoryEntryRepository(paths.project_root)

    def run_once(self, thread_id: str = "default") -> MemoryCuratorResult:
        state = self._thread_store.load(thread_id)
        cursor = self._load_cursor(thread_id)
        new_messages = state.messages[cursor:]
        if len(new_messages) < self._settings.min_new_messages:
            return MemoryCuratorResult(
                processed_messages=0,
                created=0,
                updated=0,
                ignored=0,
                log_path=self._memory_log_path(),
            )

        source_ref = f"thread:{thread_id}:{cursor}-{len(state.messages)}"
        actions = self._decide_actions(thread_id, state, cursor, new_messages)
        created = 0
        updated = 0
        ignored = 0
        for action in actions:
            if action.action == "create":
                self._create_entry(action, source_ref)
                created += 1
            elif action.action == "update":
                if self._update_entry(action, source_ref):
                    updated += 1
                else:
                    ignored += 1
            else:
                ignored += 1
        self._save_cursor(thread_id, len(state.messages))
        self._append_log(
            f"memory_curator thread={thread_id} source={source_ref} "
            f"processed={len(new_messages)} created={created} updated={updated} ignored={ignored}"
        )
        self._repository.reindex()
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
    ) -> list[MemoryAction]:
        prompt = [
            ChatMessage(
                role="system",
                content=(
                    "You are the NuSelf Memory Curator Agent. Decide whether new working-memory turns "
                    "should create or update long-term memory. Return only JSON with an actions array. "
                    "Prefer concise episode memories for discussion summaries. Use update only when an "
                    "existing memory id clearly matches. Allowed actions are create, update, ignore."
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    f"Thread: {thread_id}\n"
                    f"Existing summary:\n{state.summary or '(none)'}\n\n"
                    f"Existing memories:\n{self._existing_memory_context() or '(none)'}\n\n"
                    f"New turns {cursor}-{cursor + len(messages)}:\n{_render_transcript(messages)}\n\n"
                    "Return JSON like: "
                    '{"actions":[{"action":"create","type":"episode","title":"...","body":"...",'
                    '"confidence":0.7,"reason":"..."}]}'
                ),
            ),
        ]
        try:
            raw = self._llm.complete(prompt)
            actions = _parse_actions(raw)
        except (RuntimeError, ValueError):
            actions = []
        if actions:
            return actions
        return [_local_episode_action(messages)]

    def _existing_memory_context(self) -> str:
        lines: list[str] = []
        for entry in self._repository.list()[: self._settings.existing_memory_limit]:
            lines.append(f"- id={entry.id} type={entry.type} title={entry.title}: {entry.body}")
        return "\n".join(lines)

    def _create_entry(self, action: MemoryAction, source_ref: str) -> None:
        review_state: ReviewState = "reviewed" if action.type == "episode" else "draft"
        entry = MemoryEntry(
            type=action.type,
            title=action.title,
            body=action.body,
            source_refs=[source_ref],
            confidence=_clamp_confidence(action.confidence),
            review_state=review_state,
        )
        self._repository.save(entry)
        self._append_log(f"created entry={entry.id} type={entry.type} title={entry.title!r} reason={action.reason!r}")

    def _update_entry(self, action: MemoryAction, source_ref: str) -> bool:
        if action.entry_id is None:
            return False
        try:
            existing = self._repository.get(action.entry_id)
        except MemoryEntryNotFound:
            return False
        updated = MemoryEntry(
            type=existing.type,
            title=action.title or existing.title,
            body=action.body or existing.body,
            tags=existing.tags,
            source_refs=[*existing.source_refs, source_ref],
            confidence=_clamp_confidence(action.confidence),
            privacy=existing.privacy,
            review_state="draft",
            id=existing.id,
            created_at=existing.created_at,
            updated_at=now_iso(),
            revisit_at=existing.revisit_at,
        )
        self._repository.save(updated)
        self._append_log(f"updated entry={updated.id} title={updated.title!r} reason={action.reason!r}")
        return True

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


def _local_episode_action(messages: list[ThreadMessage]) -> MemoryAction:
    user_messages = [message.content for message in messages if message.role == "user"]
    title_source = user_messages[-1] if user_messages else "Conversation update"
    title = _compact(title_source, 80)
    body = _compact(_render_transcript(messages), 600)
    return MemoryAction(
        action="create",
        type="episode",
        title=f"Conversation: {title}",
        body=body,
        confidence=0.45,
        reason="local fallback summary",
    )


def _parse_actions(raw: str) -> list[MemoryAction]:
    parsed: object = json.loads(raw)
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
    if value in {"source_note", "profile_fact", "belief", "style_trait", "episode", "open_question", "instruction"}:
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


def _compact(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(limit - 3, 0)].rstrip() + "..."
