from __future__ import annotations

from collections.abc import Mapping

import pytest

from nuself.reason.job_contracts import (
    REASON_OUTPUT_JOB_NAME,
    build_reason_job_definition_registry,
)
from nuself.runtime.jobs import JobMessage


def _message(
    producer: str,
    payload: Mapping[str, object] | None = None,
) -> JobMessage:
    return JobMessage.create(
        name=REASON_OUTPUT_JOB_NAME,
        producer=producer,
        job_id="job-1",
        resource_id="thread-1",
        payload=payload,
    )


@pytest.mark.parametrize(
    "message",
    (
        _message("reasoning"),
        _message(
            "reasoning",
            {"mode": "narrative", "output_format": "markdown"},
        ),
        _message("daemon_retry", {"attempt": 2}),
        _message("daemon_reconciliation"),
    ),
)
def test_reason_export_job_contract_accepts_canonical_messages(
    message: JobMessage,
) -> None:
    build_reason_job_definition_registry().validate(message)


@pytest.mark.parametrize(
    "message",
    (
        _message("unknown"),
        _message("reasoning", {"mode": "narrative"}),
        _message(
            "reasoning",
            {"mode": "invalid", "output_format": "markdown"},
        ),
        _message("daemon_retry", {"attempt": 0}),
        _message("daemon_retry", {"attempt": 1, "extra": True}),
        _message("daemon_reconciliation", {"unexpected": True}),
    ),
)
def test_reason_export_job_contract_rejects_invalid_messages(
    message: JobMessage,
) -> None:
    with pytest.raises(ValueError):
        build_reason_job_definition_registry().validate(message)
