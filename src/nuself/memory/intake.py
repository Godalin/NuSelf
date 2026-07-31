"""Memory intake agent for manual memory additions."""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import cast

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from nuself.agent.structured import StructuredAgent, default_structured_agent
from nuself.domain.memory import MemoryEntryType, MemoryTypeRegistry, default_memory_type_registry
from nuself.profile.contracts import ProfileRepositoryPort

WORD_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


class IntakeResultOutput(BaseModel):
    """Structured memory intake result from the LLM."""

    model_config = ConfigDict(strict=True, extra="forbid")

    type: str = Field(description="Memory entry type.")
    title: str = Field(description="Concise memory entry title.")
    tags: list[str] = Field(min_length=1, max_length=4, description="1-4 short tags.")
    confidence: float = Field(ge=0, le=1, description="Confidence from 0.0 to 1.0.")
    importance: float = Field(ge=0, le=1, description="Importance from 0.0 to 1.0.")


@dataclass(frozen=True)
class MemoryIntakeResult:
    """Normalized memory fields inferred from user-provided text."""

    type: MemoryEntryType
    title: str
    body: str
    tags: tuple[str, ...] = ()
    confidence: float = 0.7
    importance: float = 0.5


class MemoryIntakeAgent:
    """Infer memory entry fields from a manually supplied note."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        agent: StructuredAgent[IntakeResultOutput] | None = None,
        profile_repository: ProfileRepositoryPort,
        registry: MemoryTypeRegistry | None = None,
    ) -> None:
        self._profile_repository = profile_repository
        self._agent = agent or default_structured_agent(
            IntakeResultOutput,
            project_root=project_root,
            component="memory",
        )
        self._registry = registry or default_memory_type_registry()

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
            importance=inferred.importance,
        )

    def _infer_with_llm(self, body: str) -> MemoryIntakeResult:
        prompt = [
            SystemMessage(
                content=(
                    "You are the NuSelf Memory Intake Agent. Classify a user-supplied memory note into a "
                    "durable memory entry. "
                    f"Allowed types are {', '.join(self._registry.names())}. Write a concise "
                    "title and 1-4 short tags. Do not copy raw chat transcript markers into the title. Consider "
                    "existing profile items when the note is a duplicate or refinement of already-derived context."
                ),
            ),
            HumanMessage(
                content=(
                    f"Memory note:\n{body}\n\n"
                    f"Existing profile items:\n{self._existing_profile_context(body) or '(none)'}\n\n"
                    "Classify the note into the required structured response."
                ),
            ),
        ]
        try:
            output = self._agent.invoke(prompt)
            return _intake_result_from_output(
                output,
                allowed_types=self._registry.names(),
            )
        except (RuntimeError, ValueError) as exc:
            raise ValueError(
                "memory intake agent unavailable or returned invalid structured output"
            ) from exc

    def _existing_profile_context(self, body: str) -> str:
        matches = self._profile_repository.search(body)
        if not matches:
            for token in WORD_RE.findall(body.casefold()):
                for item in self._profile_repository.search(token):
                    if item not in matches:
                        matches.append(item)
        lines: list[str] = []
        for item in matches[:5]:
            tags = f" tags={','.join(item.tags)}" if item.tags else ""
            sources = f" sources={','.join(item.source_refs)}" if item.source_refs else ""
            lines.append(f"- id={item.id} type={item.type} title={item.title}{tags}{sources}: {item.body}")
        return "\n".join(lines)


def _intake_result_from_output(
    output: IntakeResultOutput,
    *,
    allowed_types: tuple[str, ...] | None = None,
) -> MemoryIntakeResult:
    memory_type = _memory_type(output.type, allowed_types=allowed_types)
    title = output.title.strip()
    tags = _normalize_tags(output.tags)
    if title == "":
        raise ValueError("memory intake response must include a title")
    if not tags:
        raise ValueError("memory intake response must include tags")
    return MemoryIntakeResult(
        type=memory_type,
        title=title,
        body="",
        tags=tags,
        confidence=output.confidence,
        importance=output.importance,
    )
def _memory_type(value: str, *, allowed_types: tuple[str, ...] | None = None) -> MemoryEntryType:
    names = allowed_types or default_memory_type_registry().names()
    if value in names:
        return cast(MemoryEntryType, value)
    raise ValueError(f"unsupported memory type: {value}")


def _normalize_tags(tags: list[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for item in tags:
        clean = item.strip()
        if clean == "" or clean in seen:
            continue
        result.append(clean)
        seen.add(clean)
    return tuple(result)
