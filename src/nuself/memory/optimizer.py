"""Low-frequency optimizer for existing long-term memory entries."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal, TypeAlias, cast

from nuself.config import ensure_runtime_dirs, runtime_paths
from nuself.domain.memory import MemoryCandidate, MemoryEntry, MemoryEntryType, MemoryEvidence, MemoryObject, MemoryTypeRegistry, default_memory_type_registry, now_iso
from nuself.llm import ChatLLM, ChatMessage, default_llm
from nuself.memory.repository import MemoryCandidateRepository, MemoryEntryNotFound, MemoryEntryRepository
from nuself.profile.repository import ProfileItemRepository

MemoryOptimizeActionType: TypeAlias = Literal["update", "delete", "ignore"]
OptimizeDecisionStatus: TypeAlias = Literal["ready", "deferred"]


@dataclass(frozen=True)
class MemoryOptimizerSettings:
    """Policy for one long-term memory optimization run."""

    memory_limit: int = 50


@dataclass(frozen=True)
class MemoryOptimizerResult:
    """Summary of one memory optimization run."""

    reviewed: int
    updated: int
    deleted: int
    ignored: int
    log_path: Path

    @property
    def changed(self) -> bool:
        return self.updated > 0 or self.deleted > 0

    def summary(self) -> str:
        return f"reviewed={self.reviewed} updated={self.updated} deleted={self.deleted} ignored={self.ignored}"


@dataclass(frozen=True)
class MemoryOptimizeAction:
    """One structured action proposed by the memory optimizer agent."""

    action: MemoryOptimizeActionType
    entry_id: str | None = None
    title: str = ""
    body: str = ""
    type: MemoryEntryType | None = None
    tags: tuple[str, ...] | None = None
    confidence: float | None = None
    reason: str = ""


@dataclass(frozen=True)
class MemoryOptimizeDecision:
    """Structured decision returned by the optimizer agent."""

    status: OptimizeDecisionStatus
    actions: tuple[MemoryOptimizeAction, ...] = ()
    reason: str = ""


class MemoryOptimizer:
    """Consolidate existing long-term memory entries with agent decisions."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        llm: ChatLLM | None = None,
        settings: MemoryOptimizerSettings | None = None,
        repository: MemoryEntryRepository | None = None,
        candidate_repository: MemoryCandidateRepository | None = None,
        profile_repository: ProfileItemRepository | None = None,
        registry: MemoryTypeRegistry | None = None,
    ) -> None:
        paths = runtime_paths(project_root)
        self._paths = paths
        self._llm = llm or default_llm(paths.project_root)
        self._settings = settings or MemoryOptimizerSettings()
        self._repository = repository or MemoryEntryRepository(paths.project_root)
        self._profile_repository = profile_repository or ProfileItemRepository(paths.project_root)
        self._candidate_repository = candidate_repository or MemoryCandidateRepository(
            paths.project_root,
            entry_repository=self._repository,
        )
        self._registry = registry or default_memory_type_registry()

    def run_once(self) -> MemoryOptimizerResult:
        entries = self._repository.list()[: max(self._settings.memory_limit, 1)]
        if not entries:
            return MemoryOptimizerResult(
                reviewed=0,
                updated=0,
                deleted=0,
                ignored=0,
                log_path=self._memory_log_path(),
            )

        decision = self._decide_actions(entries)
        if decision.status == "deferred":
            self._append_log(f"memory_optimizer_deferred reviewed=0 reason={decision.reason!r}")
            return MemoryOptimizerResult(
                reviewed=0,
                updated=0,
                deleted=0,
                ignored=0,
                log_path=self._memory_log_path(),
            )

        source_ref = f"memory_optimize:{now_iso()}"
        updated = 0
        deleted = 0
        ignored = 0
        for action in decision.actions:
            if action.action == "update":
                if self._update_candidate(action, source_ref):
                    updated += 1
                else:
                    ignored += 1
            elif action.action == "delete":
                if self._delete_candidate(action, source_ref):
                    deleted += 1
                else:
                    ignored += 1
            else:
                ignored += 1
        self._append_log(
            f"memory_optimizer reviewed={len(entries)} updated={updated} deleted={deleted} ignored={ignored}"
        )
        return MemoryOptimizerResult(
            reviewed=len(entries),
            updated=updated,
            deleted=deleted,
            ignored=ignored,
            log_path=self._memory_log_path(),
        )

    def _decide_actions(self, entries: list[MemoryEntry]) -> MemoryOptimizeDecision:
        prompt = [
            ChatMessage(
                role="system",
                content=(
                    "You are the NuSelf Memory Optimizer Agent. Clean up existing long-term memory entries. "
                    "Return only JSON with an actions array. Allowed actions are update, delete, ignore. "
                    "Be conservative: preserve unique user preferences, goals, concepts, decisions, instructions, "
                    "beliefs, open questions, and important episodes. Prefer merging duplicate or overlapping entries by "
                    "updating the strongest entry and deleting only entries whose content is fully represented "
                    "elsewhere. Rewrite messy entries into clear compressed summaries. Consider existing profile items "
                    "when deciding whether a memory entry is truly duplicate or should be refined instead. Never create "
                    "new entries in this task and never copy raw chat transcripts into memory bodies."
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    "Existing memory entries:\n"
                    f"{_render_entries(entries)}\n\n"
                    "Existing profile items:\n"
                    f"{self._existing_profile_context()}\n\n"
                    "Return JSON like: "
                    '{"actions":[{"action":"update","entry_id":"mem_...","type":"belief",'
                    '"title":"...","body":"...","tags":["..."],"confidence":0.8,"reason":"merged duplicates"},'
                    '{"action":"delete","entry_id":"mem_...","reason":"fully merged into mem_..."},'
                    '{"action":"ignore","entry_id":"mem_...","reason":"already clear"}]}'
                ),
            ),
        ]
        try:
            raw = self._llm.complete(prompt)
            actions = _parse_optimize_actions(raw)
        except (RuntimeError, ValueError):
            return MemoryOptimizeDecision(
                status="deferred",
                reason="optimizer agent unavailable or returned invalid JSON",
            )
        if actions:
            return MemoryOptimizeDecision(status="ready", actions=tuple(actions))
        return MemoryOptimizeDecision(status="deferred", reason="optimizer agent returned no valid actions")

    def _existing_profile_context(self) -> str:
        lines: list[str] = []
        for item in self._profile_repository.list()[: self._settings.memory_limit]:
            tags = f" tags={','.join(item.tags)}" if item.tags else ""
            sources = f" sources={','.join(item.source_refs)}" if item.source_refs else ""
            lines.append(f"- id={item.id} type={item.type} title={item.title}{tags}{sources}: {item.body}")
        return "\n".join(lines)

    def _update_candidate(self, action: MemoryOptimizeAction, source_ref: str) -> bool:
        if action.entry_id is None or action.title == "" or action.body == "":
            return False
        try:
            existing = self._repository.get(action.entry_id)
        except MemoryEntryNotFound:
            return False
        incoming = MemoryObject(
            type=action.type or existing.type,
            payload={
                "title": action.title,
                "body": action.body,
                "tags": list(action.tags) if action.tags is not None else existing.tags,
            },
            confidence=_clamp_confidence(action.confidence if action.confidence is not None else existing.confidence),
        )
        merged = self._registry.merge(existing.to_memory_object(), incoming)
        merged_title = cast(str, merged.payload.get("title", action.title))
        merged_body = cast(str, merged.payload.get("body", action.body))
        merged_tags = cast(list[str], merged.payload.get("tags", list(action.tags) if action.tags is not None else existing.tags))
        candidate = MemoryCandidate(
            action="update",
            type=action.type or existing.type,
            title=merged_title,
            body=merged_body,
            tags=merged_tags,
            source_refs=[source_ref],
            evidence=[MemoryEvidence(source_type="optimizer", source_ref=source_ref, summary=action.reason)],
            confidence=_clamp_confidence(action.confidence if action.confidence is not None else existing.confidence),
            privacy=existing.privacy,
            reason=action.reason,
            target_entry_id=existing.id,
            observed_at=existing.observed_at,
            valid_from=existing.valid_from,
            valid_until=existing.valid_until,
            temporal_note=existing.temporal_note,
            relations=existing.relations,
        )
        self._candidate_repository.save(candidate)
        self._append_log(f"optimized candidate={candidate.id} target={existing.id} title={candidate.title!r}")
        return True

    def _delete_candidate(self, action: MemoryOptimizeAction, source_ref: str) -> bool:
        if action.entry_id is None:
            return False
        try:
            existing = self._repository.get(action.entry_id)
        except MemoryEntryNotFound:
            return False
        candidate = MemoryCandidate(
            action="delete",
            type=existing.type,
            title=existing.title,
            body=existing.body,
            tags=existing.tags,
            source_refs=[source_ref],
            evidence=[MemoryEvidence(source_type="optimizer", source_ref=source_ref, summary=action.reason)],
            confidence=existing.confidence,
            privacy=existing.privacy,
            reason=action.reason,
            target_entry_id=existing.id,
            observed_at=existing.observed_at,
            valid_from=existing.valid_from,
            valid_until=existing.valid_until,
            temporal_note=existing.temporal_note,
            relations=existing.relations,
        )
        self._candidate_repository.save(candidate)
        self._append_log(f"deleted candidate={candidate.id} target={existing.id} reason={action.reason!r}")
        return True

    def _memory_log_path(self) -> Path:
        return self._paths.logs_dir / "memory.log"

    def _append_log(self, message: str) -> None:
        ensure_runtime_dirs(self._paths)
        with self._memory_log_path().open("a", encoding="utf-8") as log_file:
            log_file.write(f"{now_iso()} {message}\n")


def _render_entries(entries: list[MemoryEntry]) -> str:
    lines: list[str] = []
    for entry in entries:
        tags = ", ".join(entry.tags) if entry.tags else "-"
        lines.append(
            "\n".join(
                [
                    f"id: {entry.id}",
                    f"type: {entry.type}",
                    f"title: {entry.title}",
                    f"tags: {tags}",
                    f"confidence: {entry.confidence}",
                    f"review_state: {entry.review_state}",
                    f"body: {entry.body}",
                    "",
                ]
            )
        )
    return "\n".join(lines).strip()


def _parse_optimize_actions(raw: str) -> list[MemoryOptimizeAction]:
    parsed: object = json.loads(_extract_json_object(raw))
    if not isinstance(parsed, dict):
        return []
    actions_value = cast(dict[str, object], parsed).get("actions")
    if not isinstance(actions_value, list):
        return []
    actions: list[MemoryOptimizeAction] = []
    for item in cast(list[object], actions_value):
        if not isinstance(item, dict):
            continue
        action = _parse_optimize_action(cast(dict[str, object], item))
        if action is not None:
            actions.append(action)
    return actions

def _parse_optimize_action(raw: dict[str, object]) -> MemoryOptimizeAction | None:
    action_value = raw.get("action")
    if action_value not in {"update", "delete", "ignore"}:
        return None
    entry_id = _optional_string_field(raw, "entry_id")
    if entry_id is None:
        return None
    title = _string_field(raw, "title")
    body = _string_field(raw, "body")
    if action_value == "update" and (title == "" or body == "" or _looks_like_raw_transcript(body)):
        return None
    return MemoryOptimizeAction(
        action=cast(MemoryOptimizeActionType, action_value),
        entry_id=entry_id,
        title=title,
        body=body,
        type=_optional_memory_type(raw.get("type")),
        tags=_optional_string_tuple(raw.get("tags")),
        confidence=_optional_number_field(raw, "confidence"),
        reason=_string_field(raw, "reason"),
    )


def _optional_memory_type(value: object) -> MemoryEntryType | None:
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
    return None


def _string_field(raw: dict[str, object], field_name: str) -> str:
    value = raw.get(field_name)
    return value if isinstance(value, str) else ""


def _optional_string_field(raw: dict[str, object], field_name: str) -> str | None:
    value = raw.get(field_name)
    return value if isinstance(value, str) and value != "" else None


def _optional_string_tuple(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list):
        return None
    result: list[str] = []
    for item in cast(list[object], value):
        if isinstance(item, str) and item != "":
            result.append(item)
    return tuple(result)


def _optional_number_field(raw: dict[str, object], field_name: str) -> float | None:
    value = raw.get(field_name)
    if isinstance(value, int | float):
        return float(value)
    return None


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
