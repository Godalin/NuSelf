"""Golden conversation fixtures and local evaluation runner."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import cast

from langchain_core.messages import BaseMessage

from nuself.agent.chat.types import (
    ChatResult,
    ChatStructuredOutput,
    ConversationTurnState,
)
from nuself.memory.model import MemoryEntry


@dataclass(frozen=True)
class FixtureMemoryEntry:
    """Memory entry shape inside a golden fixture."""

    type: str
    title: str
    body: str
    tags: list[str] = field(default_factory=lambda: [])

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "FixtureMemoryEntry":
        return cls(
            type=_expect_str(data, "type"),
            title=_expect_str(data, "title"),
            body=_expect_str(data, "body"),
            tags=_expect_str_list(data, "tags"),
        )

    def to_domain(self) -> MemoryEntry:
        return MemoryEntry(
            type=self.type,  # type: ignore[arg-type]
            title=self.title,
            body=self.body,
            tags=list(self.tags),
        )


@dataclass(frozen=True)
class FixtureExpectations:
    """Assertions for one golden fixture."""

    answer_contains: tuple[str, ...] = ()
    evidence_references_count_min: int = 0
    epistemic_status: str | None = None
    confidence_min: float | None = None
    banned_patterns: tuple[str, ...] = ()

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "FixtureExpectations":
        return cls(
            answer_contains=tuple(_optional_str_list(data, "answer_contains")),
            evidence_references_count_min=_optional_int_default(
                data,
                "evidence_references_count_min",
                default=0,
            ),
            epistemic_status=_optional_str(data, "epistemic_status"),
            confidence_min=_optional_float(data, "confidence_min"),
            banned_patterns=tuple(_optional_str_list(data, "banned_patterns")),
        )


@dataclass(frozen=True)
class EvalFixture:
    """One golden conversation fixture."""

    name: str
    conversation_id: str
    user_message: str
    memory_entries: tuple[FixtureMemoryEntry, ...]
    response: ChatStructuredOutput
    expectations: FixtureExpectations

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "EvalFixture":
        raw_entries_raw = data.get("memory_entries", [])
        if not isinstance(raw_entries_raw, list):
            raise ValueError("memory_entries must be a list")
        raw_entries = cast(list[object], raw_entries_raw)
        entries: list[FixtureMemoryEntry] = []
        for item in raw_entries:
            if isinstance(item, dict):
                entries.append(FixtureMemoryEntry.from_wire(cast(dict[str, object], item)))
        expectations_raw = data.get("expectations")
        if not isinstance(expectations_raw, dict):
            raise ValueError("expectations must be an object")
        response_raw = data.get("response")
        if not isinstance(response_raw, dict):
            raise ValueError("response must be an object")
        return cls(
            name=_expect_str(data, "name"),
            conversation_id=_expect_str(data, "conversation_id"),
            user_message=_expect_str(data, "user_message"),
            memory_entries=tuple(entries),
            response=ChatStructuredOutput.model_validate(response_raw),
            expectations=FixtureExpectations.from_wire(cast(dict[str, object], expectations_raw)),
        )

    @classmethod
    def from_json_file(cls, path: Path) -> "EvalFixture":
        raw: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"fixture must contain an object: {path}")
        return cls.from_wire(cast(dict[str, object], raw))


@dataclass(frozen=True)
class EvalResult:
    """Outcome from running one fixture."""

    fixture_name: str
    passed: bool
    score: float
    failures: tuple[str, ...]


class FixtureResponseService:
    """Return the fixture's typed response without emulating a model protocol."""

    def __init__(self, response: ChatStructuredOutput) -> None:
        self.response = response
        self.calls: list[list[BaseMessage]] = []

    def complete(
        self,
        prompt: list[BaseMessage],
    ) -> ChatStructuredOutput:
        self.calls.append(list(prompt))
        return self.response

    def finalize(
        self,
        state: ConversationTurnState,
        draft: ChatStructuredOutput,
    ) -> ChatStructuredOutput:
        return draft


def run_fixture(project_root: Path, fixture: EvalFixture) -> EvalResult:
    """Run one golden fixture and return the eval result."""
    from nuself.agent.chat.composition import compose_conversation_runtime
    from nuself.application.lifecycle import open_application_runtime

    with open_application_runtime(project_root) as runtime:
        application = runtime.application
        repo = application.memory.entries
        for entry in fixture.memory_entries:
            repo.save(entry.to_domain())

        agent = compose_conversation_runtime(
            application.paths,
            application.config,
            application.conversations,
            application.memory_service,
            application.memory.entries,
            application.reflection_service,
            application.reason_service,
            application.reason_workspace,
            application.trace,
            application.persona_prompts,
            response_service=FixtureResponseService(fixture.response),
        )
        result = agent.respond(
            fixture.user_message,
            fixture.conversation_id,
        )
    return score_result(fixture, result)


def score_result(fixture: EvalFixture, result: ChatResult) -> EvalResult:
    """Score a ChatResult against fixture expectations."""
    exp = fixture.expectations
    failures: list[str] = []
    checks = 0
    passed = 0

    for phrase in exp.answer_contains:
        checks += 1
        if phrase.lower() not in result.answer.lower():
            failures.append(f"answer does not contain: {phrase!r}")
        else:
            passed += 1

    if exp.evidence_references_count_min > 0:
        checks += 1
        if len(result.evidence_references) < exp.evidence_references_count_min:
            failures.append(
                f"evidence_references count {len(result.evidence_references)} < {exp.evidence_references_count_min}"
            )
        else:
            passed += 1

    if exp.epistemic_status is not None:
        checks += 1
        if result.epistemic_status != exp.epistemic_status:
            failures.append(f"epistemic_status {result.epistemic_status!r} != {exp.epistemic_status!r}")
        else:
            passed += 1

    if exp.confidence_min is not None:
        checks += 1
        effective_confidence = result.confidence if result.confidence is not None else 0.0
        if effective_confidence < exp.confidence_min:
            failures.append(f"confidence {effective_confidence} < {exp.confidence_min}")
        else:
            passed += 1

    for pattern in exp.banned_patterns:
        checks += 1
        if pattern.lower() in result.answer.lower():
            failures.append(f"answer contains banned pattern: {pattern!r}")
        else:
            passed += 1

    score = passed / checks if checks > 0 else 1.0
    return EvalResult(
        fixture_name=fixture.name,
        passed=score >= 1.0,
        score=score,
        failures=tuple(failures),
    )


def load_fixtures(directory: Path) -> list[EvalFixture]:
    """Load all .json fixtures from a directory."""
    if not directory.exists():
        return []
    fixtures: list[EvalFixture] = []
    for path in sorted(directory.glob("*.json")):
        fixtures.append(EvalFixture.from_json_file(path))
    return fixtures


def run_eval(project_root: Path, fixtures_dir: Path) -> list[EvalResult]:
    """Run all fixtures in a directory and return results."""
    fixtures = load_fixtures(fixtures_dir)
    results: list[EvalResult] = []
    for fixture in fixtures:
        results.append(run_fixture(project_root, fixture))
    return results


# --- small helpers ---

def _expect_str(data: dict[str, object], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"field '{field_name}' must be a string")
    return value


def _expect_str_list(data: dict[str, object], field_name: str) -> list[str]:
    value = data.get(field_name, [])
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list")
    result: list[str] = []
    for raw_item in cast(list[object], value):
        if not isinstance(raw_item, str):
            raise ValueError(f"field '{field_name}' must be a list of strings")
        result.append(raw_item)
    return result


def _optional_str(data: dict[str, object], field_name: str) -> str | None:
    value = data.get(field_name)
    return value if isinstance(value, str) else None


def _optional_int(data: dict[str, object], field_name: str) -> int | None:
    value = data.get(field_name)
    if value is None:
        return None
    if type(value) is int:
        return value
    raise ValueError(f"field '{field_name}' must be an integer or null")


def _optional_int_default(
    data: dict[str, object],
    field_name: str,
    *,
    default: int,
) -> int:
    value = _optional_int(data, field_name)
    return default if value is None else value


def _optional_float(data: dict[str, object], field_name: str) -> float | None:
    value = data.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"field '{field_name}' must be a number or null")
    if isinstance(value, int | float):
        return float(value)
    raise ValueError(f"field '{field_name}' must be a number or null")


def _optional_str_list(data: dict[str, object], field_name: str) -> list[str]:
    value = data.get(field_name)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list")
    result: list[str] = []
    for raw_item in cast(list[object], value):
        if not isinstance(raw_item, str):
            raise ValueError(f"field '{field_name}' must be a list of strings")
        result.append(raw_item)
    return result
