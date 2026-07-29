from __future__ import annotations

import queue

import pytest

from nuself.runtime.jobs import JobAdmissionQueue, JobMessage


def _message(
    job_id: str,
    *,
    producer: str = "reasoning",
    resource_id: str = "thread-1",
    payload: dict[str, object] | None = None,
) -> JobMessage:
    return JobMessage.create(
        name="reason.output.export",
        producer=producer,
        job_id=job_id,
        resource_id=resource_id,
        payload=payload,
    )


def test_job_admission_coalesces_pending_and_in_flight_identity() -> None:
    admission = JobAdmissionQueue(capacity=2)
    original = _message("job-1")
    duplicate = _message(
        "job-1",
        producer="daemon_reconciliation",
        payload={"ignored_by_identity": True},
    )

    assert admission.admit(original) == "admitted"
    assert admission.admit(duplicate) == "duplicate"

    acquired = admission.get_nowait()
    assert acquired is original
    assert admission.empty()
    assert admission.admit(duplicate) == "duplicate"

    admission.complete(acquired)
    assert admission.admit(duplicate) == "admitted"


def test_job_admission_bounds_distinct_pending_work() -> None:
    admission = JobAdmissionQueue(capacity=1)

    assert admission.admit(_message("job-1")) == "admitted"
    assert admission.admit(_message("job-2")) == "full"
    assert admission.pending_count == 1


def test_job_admission_drain_releases_only_pending_identity() -> None:
    admission = JobAdmissionQueue(capacity=2)
    in_flight = _message("job-active")
    pending = _message("job-pending")
    assert admission.admit(in_flight) == "admitted"
    assert admission.admit(pending) == "admitted"
    assert admission.get_nowait() is in_flight

    assert admission.drain() == (pending,)
    assert admission.admit(pending) == "admitted"
    assert admission.admit(in_flight) == "duplicate"

    admission.complete(in_flight)


def test_job_admission_rejects_invalid_capacity_and_empty_reads() -> None:
    for capacity in (0, -1, True):
        with pytest.raises(ValueError, match="capacity"):
            JobAdmissionQueue(capacity)  # type: ignore[arg-type]

    admission = JobAdmissionQueue(capacity=1)
    with pytest.raises(queue.Empty):
        admission.get_nowait()
