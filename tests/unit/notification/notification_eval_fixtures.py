"""Structured evaluation fixtures for notification behavior."""

from __future__ import annotations

import json
from pathlib import Path

from nuself.notification_eval import run_notification_eval

FIXTURES_DIR = (
    Path(__file__).parents[2] / "fixtures" / "notifications"
)


def test_notification_eval_returns_one_result_per_scenario(
    tmp_path: Path,
) -> None:
    results = run_notification_eval(tmp_path, FIXTURES_DIR)

    assert len(results) == 11
    assert all(result.passed for result in results)
    assert {
        "deep_link/basic-conversation",
        "outbox_delivery/mark-sent",
        "reflection_scheduler/in-cooldown",
    } <= {result.fixture_name for result in results}


def test_notification_eval_reports_structured_failure(
    tmp_path: Path,
) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "deep_link.json").write_text(
        json.dumps(
            {
                "component": "deep_link",
                "scenarios": [
                    {
                        "name": "wrong-expectation",
                        "url": "nuself://conversation/actual",
                        "expected_conversation_id": "expected",
                        "expected_message": None,
                        "should_succeed": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    results = run_notification_eval(
        tmp_path / "storage",
        fixtures,
    )

    assert len(results) == 1
    assert not results[0].passed
    assert results[0].score == 0.0
    assert "conversation_id" in results[0].failures[0]
