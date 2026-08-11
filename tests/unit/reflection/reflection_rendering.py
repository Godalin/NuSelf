"""Compact Reflection provenance rendering tests."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from langchain_core.messages import BaseMessage

from nuself.reflection.rendering import (
    LLMChineseTranslator,
    ProvenanceRenderer,
    TranslationItem,
    TranslationOutput,
)
from nuself.trace.provenance import ProvenanceChain, ProvenanceNode


class _Translator:
    def __init__(self, translations: tuple[str, ...]) -> None:
        self._translations = translations
        self.inputs: list[tuple[str, ...]] = []

    def translate(self, bodies: tuple[str, ...]) -> tuple[str, ...]:
        self.inputs.append(bodies)
        return self._translations


class _TranslationAgent:
    def __init__(self, output: TranslationOutput) -> None:
        self._output = output
        self.messages: list[Sequence[BaseMessage]] = []

    def invoke(self, messages: Sequence[BaseMessage]) -> TranslationOutput:
        self.messages.append(messages)
        return self._output


def test_renderer_uses_short_ids_spacing_and_selective_translation() -> None:
    translator = _Translator(("英文节点的中文翻译。",))
    renderer = ProvenanceRenderer(translator)
    chain = ProvenanceChain((
        ProvenanceNode("memory:mem_123", "An English memory summary."),
        ProvenanceNode("reflection:reflection-456", "已经是中文正文。"),
    ))

    rendered = renderer.render(chain)
    blocks = rendered.split("\n\n")

    assert len(blocks) == 2
    assert blocks[0].splitlines()[0].startswith("mem-")
    assert len(blocks[0].splitlines()[0]) == 10
    assert blocks[0].splitlines()[1:] == [
        "An English memory summary.",
        "中文：英文节点的中文翻译。",
    ]
    assert blocks[1].splitlines()[1:] == ["已经是中文正文。"]
    assert blocks[1].splitlines()[0].startswith("refl-")
    assert translator.inputs == [("An English memory summary.",)]


def test_renderer_is_stable_and_can_skip_translation() -> None:
    translator = _Translator(())
    renderer = ProvenanceRenderer(translator)
    chain = ProvenanceChain(
        (ProvenanceNode("trace:trace-123", "English body."),),
        truncated=True,
    )

    first = renderer.render(chain, translate=False)
    second = renderer.render(chain, translate=False)

    assert first == second
    assert first.split("\n\n")[-1] == "…\n来源链已截断"
    assert translator.inputs == []


def test_llm_translator_requires_complete_position_preserving_output(
    tmp_path: Path,
) -> None:
    agent = _TranslationAgent(
        TranslationOutput(
            translations=[
                TranslationItem(position=1, chinese="第二条。"),
                TranslationItem(position=0, chinese="第一条。"),
            ]
        )
    )
    translator = LLMChineseTranslator(tmp_path, agent=agent)

    assert translator.translate(("First.", "Second.")) == (
        "第一条。",
        "第二条。",
    )
    assert "[0] First." in str(agent.messages[0][-1].content)
