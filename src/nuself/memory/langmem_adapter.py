# pyright: reportMissingTypeStubs=false
"""Optional LangMem-based memory curator adapter."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from nuself.agent.messages import ChatMessage
from nuself.domain.memory import MemoryCandidate, MemoryEvidence, MemoryEntryType
from nuself.llm import LLMSettings
def _title_from_body(body: str) -> str:
    compact = " ".join(body.split())
    if len(compact) <= 48:
        return compact
    return compact[:45].rstrip() + "..."


def _to_langmem_messages(messages: list[ChatMessage]) -> list[dict[str, str]]:
    return [{"role": message.role, "content": message.content} for message in messages]


def _memory_type_from_content(content: str) -> MemoryEntryType:
    normalized = content.casefold()
    if "prefer" in normalized or "like" in normalized or "rather" in normalized:
        return "preference"
    if "goal" in normalized or "want to" in normalized or "plan to" in normalized:
        return "goal"
    if "concept" in normalized or "means" in normalized or "definition" in normalized:
        return "concept"
    if "remember to" in normalized or "always" in normalized or "never" in normalized or "should" in normalized:
        return "instruction"
    if "believe" in normalized or "think" in normalized or "is true" in normalized:
        return "belief"
    return "episode"


class LangMemCurator:
    """Extract memory candidates using LangMem's memory manager."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        settings: LLMSettings | None = None,
    ) -> None:
        self._settings = settings or LLMSettings.from_project(project_root)
        self._manager: object | None = None

    def _ensure_manager(self) -> object:
        if self._manager is not None:
            return self._manager
        try:
            from langchain_openai import ChatOpenAI
            from langmem import create_memory_manager
        except ImportError as exc:
            raise RuntimeError("langmem or langchain-openai is not installed") from exc
        if self._settings.api_key.strip() == "":
            raise RuntimeError("LLM API key is not configured")
        from pydantic import SecretStr

        llm = ChatOpenAI(
            base_url=self._settings.base_url,
            api_key=SecretStr(self._settings.api_key),
            model=self._settings.model,
        )
        self._manager = create_memory_manager(llm)
        return self._manager

    def extract(self, messages: list[ChatMessage], source_ref: str = "langmem") -> list[MemoryCandidate]:
        manager = self._ensure_manager()
        langmem_messages = _to_langmem_messages(messages)
        try:
            result = manager.invoke({"messages": langmem_messages})  # type: ignore[union-attr]
        except Exception as exc:
            raise RuntimeError(f"langmem extraction failed: {exc}") from exc
        candidates: list[MemoryCandidate] = []
        for extracted in cast(list[object], result):
            content = str(getattr(getattr(extracted, "content", None), "content", ""))
            if not content:
                continue
            memory_type = _memory_type_from_content(content)
            candidate = MemoryCandidate(
                action="create",
                type=memory_type,
                title=_title_from_body(content),
                body=content,
                tags=[memory_type],
                source_refs=[source_ref],
                evidence=[
                    MemoryEvidence(
                        source_type="thread",
                        source_ref=source_ref,
                        summary="extracted by langmem",
                    )
                ],
                confidence=0.7,
                reason="langmem extraction",
            )
            candidates.append(candidate)
        return candidates
