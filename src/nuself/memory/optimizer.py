"""Low-frequency optimizer for existing long-term memory entries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias, cast

from pydantic import BaseModel, Field

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


class OptimizeActionItem(BaseModel):
    """One structured memory optimization action from the LLM."""

    action: Literal["update", "delete", "ignore"] = Field(description="Optimization action type.")
    entry_id: str = Field(description="Existing memory entry id.")
    title: str = Field(default="", description="Updated entry title (required for update).")
    body: str = Field(default="", description="Updated entry body (required for update).")
    type: str | None = Field(default=None, description="Optional memory entry type override.")
    tags: list[str] | None = Field(default=None, description="Optional tag list override.")
    confidence: float | None = Field(default=None, description="Optional confidence override.")
    reason: str = Field(default="", description="Reason for the action.")


class OptimizeActionsOutput(BaseModel):
    """Structured optimizer actions response from the LLM."""

    actions: list[OptimizeActionItem] = Field(description="Memory optimization actions.")


class MemoryOptimizer:

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
            actions = _parse_optimize_actions(raw, allowed_types=self._registry.names())
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


def _parse_optimize_actions(raw: str, *, allowed_types: tuple[str, ...]) -> list[MemoryOptimizeAction]:
    extracted = _extract_json_object(raw)
    output = OptimizeActionsOutput.model_validate_json(extracted)
    actions: list[MemoryOptimizeAction] = []
    for item in output.actions:
        action = _optimize_action_from_item(item, allowed_types=allowed_types)
        if action is not None:
            actions.append(action)
    return actions


def _optimize_action_from_item(
    item: OptimizeActionItem,
    *,
    allowed_types: tuple[str, ...],
) -> MemoryOptimizeAction | None:
    if item.entry_id == "":
        return None
    if item.action == "update" and (item.title == "" or item.body == "" or _looks_like_raw_transcript(item.body)):
        return None
    try:
        memory_type = _optional_memory_type(item.type, allowed_types=allowed_types)
    except ValueError:
        return None
    return MemoryOptimizeAction(
        action=item.action,
        entry_id=item.entry_id,
        title=item.title,
        body=item.body,
        type=memory_type,
        tags=tuple(item.tags) if item.tags is not None else None,
        confidence=item.confidence,
        reason=item.reason,
    )


def _optional_memory_type(value: str | None, *, allowed_types: tuple[str, ...]) -> MemoryEntryType | None:
    if value is None:
        return None
    if value in allowed_types:
        return cast(MemoryEntryType, value)
    raise ValueError(f"unsupported memory type: {value}")


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
