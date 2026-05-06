"""Memory intake agent for manual memory additions."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import cast

from nuself.domain.memory import MemoryEntryType
from nuself.llm import ChatLLM, ChatMessage, default_llm


@dataclass(frozen=True)
class MemoryIntakeResult:
    """Normalized memory fields inferred from user-provided text."""

    type: MemoryEntryType
    title: str
    body: str
    tags: tuple[str, ...] = ()
    confidence: float = 0.7


class MemoryIntakeAgent:
    """Infer memory entry fields from a manually supplied note."""

    def __init__(self, project_root: Path | None = None, *, llm: ChatLLM | None = None) -> None:
        self._llm = llm or default_llm(project_root)

    def infer(
        self,
        *,
        body: str,
        title: str | None = None,
        memory_type: MemoryEntryType | None = None,
        tags: list[str] | None = None,
    ) -> MemoryIntakeResult:
        normalized_body = " ".join(body.split())
        if normalized_body == "":
            raise ValueError("memory body must not be empty")

        if memory_type is not None and title is not None:
            return MemoryIntakeResult(
                type=memory_type,
                title=title,
                body=normalized_body,
                tags=tuple(tags or ()),
                confidence=0.8,
            )

        inferred = self._infer_with_llm(normalized_body)
        return MemoryIntakeResult(
            type=memory_type or inferred.type,
            title=title or inferred.title,
            body=normalized_body,
            tags=tuple(tags or inferred.tags),
            confidence=inferred.confidence,
        )

    def _infer_with_llm(self, body: str) -> MemoryIntakeResult:
        prompt = [
            ChatMessage(
                role="system",
                content=(
                    "You are the NuSelf Memory Intake Agent. Classify a user-supplied memory note into a "
                    "durable memory entry. Return only JSON. Allowed types are source_note, profile_fact, "
                    "belief, preference, style_trait, episode, open_question, instruction. Write a concise "
                    "title and 0-4 short tags. Do not copy raw chat transcript markers into the title."
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    f"Memory note:\n{body}\n\n"
                    "Return JSON like: "
                    '{"type":"preference","title":"Concise CLI output","tags":["cli"],"confidence":0.8}'
                ),
            ),
        ]
        try:
            raw = self._llm.complete(prompt)
            return _parse_intake_result(raw)
        except (RuntimeError, ValueError, json.JSONDecodeError):
            return _infer_locally(body)


def _parse_intake_result(raw: str) -> MemoryIntakeResult:
    parsed: object = json.loads(_extract_json_object(raw))
    if not isinstance(parsed, dict):
        raise ValueError("memory intake response must be an object")
    data = cast(dict[str, object], parsed)
    memory_type = _memory_type(data.get("type"))
    title = _string_field(data, "title")
    if title == "":
        raise ValueError("memory intake response must include a title")
    return MemoryIntakeResult(
        type=memory_type,
        title=title,
        body="",
        tags=_string_tuple(data.get("tags")),
        confidence=_clamp_confidence(_number_field(data, "confidence", 0.7)),
    )


def _infer_locally(body: str) -> MemoryIntakeResult:
    normalized = body.casefold()
    memory_type: MemoryEntryType = "episode"
    if "prefer" in normalized or "like" in normalized or "rather" in normalized:
        memory_type = "preference"
    elif "remember to" in normalized or "always" in normalized or "never" in normalized or "should" in normalized:
        memory_type = "instruction"
    elif "believe" in normalized or "think" in normalized or "is true" in normalized:
        memory_type = "belief"
    elif "?" in body:
        memory_type = "open_question"

    return MemoryIntakeResult(
        type=memory_type,
        title=_local_title(body),
        body="",
        tags=(),
        confidence=0.55,
    )


def _local_title(body: str) -> str:
    compact = " ".join(body.split())
    if len(compact) <= 48:
        return compact
    return compact[:45].rstrip() + "..."


def _extract_json_object(raw: str) -> str:
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
        stripped = "\n".join(lines).strip()
    return stripped


def _memory_type(value: object) -> MemoryEntryType:
    if value in {
        "source_note",
        "profile_fact",
        "belief",
        "preference",
        "style_trait",
        "episode",
        "open_question",
        "instruction",
    }:
        return cast(MemoryEntryType, value)
    raise ValueError(f"unsupported memory type: {value}")


def _string_field(raw: dict[str, object], field_name: str) -> str:
    value = raw.get(field_name)
    return value if isinstance(value, str) else ""


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    for item in cast(list[object], value):
        if isinstance(item, str) and item.strip() != "":
            result.append(item.strip())
    return tuple(result)


def _number_field(raw: dict[str, object], field_name: str, default: float) -> float:
    value = raw.get(field_name)
    if isinstance(value, int | float):
        return float(value)
    return default


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(value, 1.0))
