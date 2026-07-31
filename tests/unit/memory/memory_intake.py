from __future__ import annotations

# pyright: reportPrivateUsage=false

from collections.abc import Sequence
from pathlib import Path

import pytest
from langchain_core.messages import BaseMessage
from pydantic import ValidationError

from nuself.domain.profile import ProfileItem
from nuself.memory.intake import IntakeResultOutput, MemoryIntakeAgent
from nuself.profile.repository import ProfileItemRepository
from nuself.storage import _create_sqlite_backend, get_default_backend


class FakeIntakeAgent:
    def __init__(self, output: IntakeResultOutput) -> None:
        self.output = output
        self.calls: list[Sequence[BaseMessage]] = []

    def invoke(
        self,
        messages: Sequence[BaseMessage],
    ) -> IntakeResultOutput:
        self.calls.append(messages)
        return self.output


def _output(
    *,
    memory_type: str = "belief",
    title: str = "Durable memory",
    tags: list[str] | None = None,
    confidence: float = 0.8,
    importance: float = 0.6,
) -> IntakeResultOutput:
    return IntakeResultOutput(
        type=memory_type,
        title=title,
        tags=tags or ["memory"],
        confidence=confidence,
        importance=importance,
    )


def _intake(tmp_path: Path, agent: object) -> MemoryIntakeAgent:
    _create_sqlite_backend(db_path=tmp_path / "nuself.sqlite").close()
    return MemoryIntakeAgent(
        tmp_path,
        agent=agent,  # type: ignore[arg-type]
        profile_repository=ProfileItemRepository(runtime_paths(tmp_path), backend=get_default_backend(tmp_path)),
    )


def test_memory_intake_infers_goal_from_typed_agent(tmp_path: Path) -> None:
    structured_agent = FakeIntakeAgent(
        _output(
            memory_type="goal",
            title="Finish memory system planning",
            tags=["planning"],
            importance=0.7,
        )
    )

    result = _intake(tmp_path, structured_agent).infer(
        body="My goal is to finish the memory system planning."
    )

    assert result.type == "goal"


def test_memory_intake_infers_concept_from_typed_agent(tmp_path: Path) -> None:
    structured_agent = FakeIntakeAgent(
        _output(
            memory_type="concept",
            title="Temporal memory preserves change",
        )
    )

    result = _intake(tmp_path, structured_agent).infer(
        body="Temporal memory means preserving when a thought changed."
    )

    assert result.type == "concept"


def test_memory_intake_empty_body_raises_before_agent_call(tmp_path: Path) -> None:
    structured_agent = FakeIntakeAgent(_output())
    agent = _intake(tmp_path, structured_agent)

    with pytest.raises(ValueError, match="must not be empty"):
        agent.infer(body="")

    assert structured_agent.calls == []


def test_memory_intake_wraps_structured_agent_failure(tmp_path: Path) -> None:
    class BrokenAgent:
        def invoke(
            self,
            messages: Sequence[BaseMessage],
        ) -> IntakeResultOutput:
            raise RuntimeError("agent unavailable")

    agent = _intake(tmp_path, BrokenAgent())

    with pytest.raises(
        ValueError,
        match="invalid structured output",
    ):
        agent.infer(body="I prefer dark mode.")


@pytest.mark.parametrize(
    "payload",
    [
        {
            "type": "belief",
            "title": "Title",
            "tags": ["memory"],
            "confidence": 0.8,
        },
        {
            "type": "belief",
            "title": "Title",
            "tags": ["memory"],
            "importance": 0.6,
        },
        {
            "type": "belief",
            "title": "Title",
            "tags": [],
            "confidence": 0.8,
            "importance": 0.6,
        },
        {
            "type": "belief",
            "title": "Title",
            "tags": ["a", "b", "c", "d", "e"],
            "confidence": 0.8,
            "importance": 0.6,
        },
        {
            "type": "belief",
            "title": "Title",
            "tags": ["memory"],
            "confidence": 1.2,
            "importance": 0.6,
        },
        {
            "type": "belief",
            "title": "Title",
            "tags": ["memory"],
            "confidence": 0.8,
            "importance": -0.1,
        },
        {
            "type": "belief",
            "title": "Title",
            "tags": ["memory"],
            "confidence": True,
            "importance": 0.6,
        },
        {
            "type": "belief",
            "title": "Title",
            "tags": ["memory"],
            "confidence": 0.8,
            "importance": 0.6,
            "unknown": "value",
        },
    ],
)
def test_intake_schema_rejects_incomplete_or_coercive_values(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        IntakeResultOutput.model_validate(payload)


def test_memory_intake_rejects_empty_normalized_tags(tmp_path: Path) -> None:
    agent = _intake(
        tmp_path,
        FakeIntakeAgent(_output(tags=[" ", " "])),
    )

    with pytest.raises(
        ValueError,
        match="invalid structured output",
    ):
        agent.infer(body="A durable memory note.")


def test_memory_intake_includes_profile_context_in_prompt(
    tmp_path: Path,
) -> None:
    profile_repo = ProfileItemRepository(runtime_paths(tmp_path), backend=get_default_backend(tmp_path))
    profile_repo.save(
        ProfileItem(
            type="profile_fact",
            title="Concise output",
            body="Prefers concise command output.",
            tags=["cli"],
            source_refs=["source:profile:0"],
        )
    )
    structured_agent = FakeIntakeAgent(
        _output(
            memory_type="preference",
            title="Concise CLI output",
            tags=["cli"],
        )
    )
    agent = MemoryIntakeAgent(
        tmp_path,
        agent=structured_agent,
        profile_repository=profile_repo,
    )

    agent.infer(body="I prefer concise CLI output.")

    system_prompt, user_prompt = structured_agent.calls[0]
    system_content = system_prompt.text
    user_content = user_prompt.text
    assert "Consider existing profile items" in system_content
    assert "Existing profile items:" in user_content
    assert "Concise output" in user_content
from nuself.config import runtime_paths
