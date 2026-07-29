"""Tests for the evaluation runner and scoring."""

from __future__ import annotations

from pathlib import Path

import pytest

from nuself.eval import (
    EvalFixture,
    FixtureExpectations,
    FixtureMemoryEntry,
    load_fixtures,
    run_fixture,
    score_result,
)
from nuself.agent.chat import ChatResult, ChatStructuredOutput


def test_fixture_numeric_zero_is_not_treated_as_missing() -> None:
    expectations = FixtureExpectations.from_wire(
        {
            "evidence_references_count_min": 0,
            "confidence_min": 0.0,
        }
    )

    assert expectations.evidence_references_count_min == 0
    assert expectations.confidence_min == 0.0


@pytest.mark.parametrize(
    "wire",
    [
        {"evidence_references_count_min": True},
        {"confidence_min": False},
    ],
)
def test_fixture_numeric_fields_reject_booleans(
    wire: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        FixtureExpectations.from_wire(wire)


def test_score_result_passes_all_expectations() -> None:
    fixture = EvalFixture(
        name="pass",
        thread_id="t",
        user_message="hi",
        memory_entries=(),
        response=ChatStructuredOutput(answer=""),
        expectations=FixtureExpectations(
            answer_contains=("hello",),
            evidence_references_count_min=1,
            epistemic_status="grounded",
            confidence_min=0.5,
            banned_patterns=("bad",),
        ),
    )
    result = ChatResult(
        answer="hello world",
        thread_id="t",
        evidence_references=("mem_1",),
        confidence=0.8,
        epistemic_status="grounded",
    )
    eval_result = score_result(fixture, result)
    assert eval_result.passed
    assert eval_result.score == 1.0
    assert eval_result.failures == ()


def test_score_result_fails_missing_evidence() -> None:
    fixture = EvalFixture(
        name="fail",
        thread_id="t",
        user_message="hi",
        memory_entries=(),
        response=ChatStructuredOutput(answer=""),
        expectations=FixtureExpectations(
            evidence_references_count_min=1,
        ),
    )
    result = ChatResult(answer="hello", thread_id="t")
    eval_result = score_result(fixture, result)
    assert not eval_result.passed
    assert eval_result.score == 0.0
    assert any("evidence_references" in f for f in eval_result.failures)


def test_score_result_fails_banned_pattern() -> None:
    fixture = EvalFixture(
        name="banned",
        thread_id="t",
        user_message="hi",
        memory_entries=(),
        response=ChatStructuredOutput(answer=""),
        expectations=FixtureExpectations(
            banned_patterns=("always",),
        ),
    )
    result = ChatResult(answer="You always do this.", thread_id="t")
    eval_result = score_result(fixture, result)
    assert not eval_result.passed
    assert any("always" in f for f in eval_result.failures)


def test_load_fixtures_loads_json_files(tmp_path: Path) -> None:
    fixture_path = tmp_path / "test.json"
    fixture_path.write_text(
        '{"name":"x","thread_id":"t","user_message":"hi","memory_entries":[],'
        '"response":{"answer":"reply"},"expectations":{}}',
        encoding="utf-8",
    )
    fixtures = load_fixtures(tmp_path)
    assert len(fixtures) == 1
    assert fixtures[0].name == "x"


def test_run_fixture_runs_end_to_end(tmp_path: Path) -> None:
    fixture = EvalFixture(
        name="e2e",
        thread_id="t",
        user_message="What do I prefer?",
        memory_entries=(
            FixtureMemoryEntry(type="belief", title="Pref", body="I like tea.", tags=["food"]),
        ),
        response=ChatStructuredOutput(
            answer="You like tea.",
            evidence_references=["mem_1"],
            confidence=0.9,
            epistemic_status="grounded",
        ),
        expectations=FixtureExpectations(
            answer_contains=("tea",),
            evidence_references_count_min=1,
            epistemic_status="grounded",
        ),
    )
    result = run_fixture(tmp_path, fixture)
    assert result.passed
    assert result.score == 1.0
