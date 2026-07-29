from __future__ import annotations

from collections.abc import Mapping

import pytest

from nuself.reason.job_contracts import (
    REASON_OUTPUT_JOB_NAME,
    build_reason_job_definition_registry,
)
@pytest.mark.parametrize(
    ("producer", "payload"),
    (
        ("reasoning", None),
        (
            "reasoning",
            {"mode": "narrative", "output_format": "markdown"},
        ),
        ("daemon_retry", {"attempt": 2}),
        ("daemon_reconciliation", None),
    ),
)
def test_reason_export_job_contract_accepts_canonical_messages(
    producer: str,
    payload: Mapping[str, object] | None,
) -> None:
    message = build_reason_job_definition_registry().create(
        name=REASON_OUTPUT_JOB_NAME,
        producer=producer,
        job_id="job-1",
        resource_id="thread-1",
        payload=payload,
    )

    assert message.producer == producer
    assert message.payload == ({} if payload is None else payload)


@pytest.mark.parametrize(
    ("producer", "payload"),
    (
        ("unknown", None),
        ("reasoning", {"mode": "narrative"}),
        (
            "reasoning",
            {"mode": "invalid", "output_format": "markdown"},
        ),
        ("daemon_retry", {"attempt": 0}),
        ("daemon_retry", {"attempt": 1, "extra": True}),
        ("daemon_reconciliation", {"unexpected": True}),
    ),
)
def test_reason_export_job_contract_rejects_invalid_message_construction(
    producer: str,
    payload: Mapping[str, object] | None,
) -> None:
    with pytest.raises(ValueError):
        build_reason_job_definition_registry().create(
            name=REASON_OUTPUT_JOB_NAME,
            producer=producer,
            job_id="job-1",
            resource_id="thread-1",
            payload=payload,
        )
