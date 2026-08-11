"""Compact bilingual rendering for Reflection provenance."""

from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256
from pathlib import Path
import re
from typing import Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from nuself.agent.endpoint import LangChainLLMEndpoint
from nuself.agent.structured import StructuredAgent, default_structured_agent
from nuself.trace.provenance import ProvenanceChain

_ASCII_LETTER = re.compile(r"[A-Za-z]")
_HAN_CHARACTER = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


class TranslationItem(BaseModel):
    """One position-preserving Chinese translation."""

    model_config = ConfigDict(strict=True, extra="forbid")

    position: int = Field(ge=0)
    chinese: str = Field(min_length=1, max_length=400)


class TranslationOutput(BaseModel):
    """Structured translations for one bounded node batch."""

    model_config = ConfigDict(strict=True, extra="forbid")

    translations: list[TranslationItem] = Field(max_length=24)


class ChineseTranslator(Protocol):
    def translate(self, bodies: tuple[str, ...]) -> tuple[str, ...]: ...


class LLMChineseTranslator:
    """Translate one bounded batch while preserving input positions."""

    def __init__(
        self,
        project_root: Path,
        *,
        agent: StructuredAgent[TranslationOutput] | None = None,
        langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
    ) -> None:
        self._agent = agent or default_structured_agent(
            TranslationOutput,
            project_root=project_root,
            component="reflection",
            endpoints=langchain_models,
        )

    def translate(self, bodies: tuple[str, ...]) -> tuple[str, ...]:
        if not bodies:
            return ()
        numbered = "\n".join(
            f"[{position}] {body}"
            for position, body in enumerate(bodies)
        )
        output = self._agent.invoke(
            [
                SystemMessage(
                    content=(
                        "Translate every numbered provenance summary into "
                        "concise, natural Simplified Chinese. Preserve names, "
                        "IDs, numbers, and technical meaning. Return exactly "
                        "one translation for every input position."
                    )
                ),
                HumanMessage(content=numbered),
            ]
        )
        translated = {
            item.position: item.chinese.strip()
            for item in output.translations
        }
        expected = set(range(len(bodies)))
        if set(translated) != expected or len(output.translations) != len(expected):
            raise ValueError("translation output positions do not match input batch")
        values = tuple(translated[position] for position in range(len(bodies)))
        if any(not _HAN_CHARACTER.search(value) for value in values):
            raise ValueError("translation output must contain Chinese text")
        return values


class ProvenanceRenderer:
    """Render canonical chain nodes as compact, spaced display blocks."""

    def __init__(self, translator: ChineseTranslator) -> None:
        self._translator = translator

    def render(
        self,
        chain: ProvenanceChain,
        *,
        translate: bool = True,
    ) -> str:
        display_ids = _display_ids(node.ref for node in chain.nodes)
        english_positions = tuple(
            position
            for position, node in enumerate(chain.nodes)
            if _is_english(node.body)
        )
        translations: dict[int, str] = {}
        if translate and english_positions:
            translated = self._translator.translate(
                tuple(chain.nodes[position].body for position in english_positions)
            )
            if len(translated) != len(english_positions):
                raise ValueError("translator returned an incomplete batch")
            translations = dict(zip(english_positions, translated, strict=True))

        blocks: list[str] = []
        for position, (display_id, node) in enumerate(
            zip(display_ids, chain.nodes, strict=True)
        ):
            lines = [display_id, node.body]
            translation = translations.get(position)
            if translation is not None:
                lines.append(f"中文：{translation}")
            blocks.append("\n".join(lines))
        if chain.truncated:
            blocks.append("…\n来源链已截断")
        return "\n\n".join(blocks)


def _display_ids(refs: Iterable[str]) -> tuple[str, ...]:
    digests = tuple(sha256(ref.encode("utf-8")).hexdigest() for ref in refs)
    lengths = [6] * len(digests)
    while True:
        groups: dict[str, list[int]] = {}
        for position, digest in enumerate(digests):
            groups.setdefault(digest[: lengths[position]], []).append(position)
        collisions = [positions for positions in groups.values() if len(positions) > 1]
        if not collisions:
            return tuple(
                digest[:length]
                for digest, length in zip(digests, lengths, strict=True)
            )
        for positions in collisions:
            for position in positions:
                if lengths[position] >= len(digests[position]):
                    raise ValueError("duplicate provenance references cannot be abbreviated")
                lengths[position] += 1


def _is_english(body: str) -> bool:
    return bool(_ASCII_LETTER.search(body)) and not _HAN_CHARACTER.search(body)
