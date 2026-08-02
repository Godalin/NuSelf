"""Closed runtime job contracts owned by Reason."""

from __future__ import annotations

from collections.abc import Mapping

from nuself.runtime.job.definition import (
    JobDefinitionRegistry,
    RuntimeJobDefinition,
    build_job_definition_registry,
)

REASON_OUTPUT_JOB_NAME = "reason.output.export"
_OUTPUT_MODES = frozenset({"outline", "narrative", "report", "summary"})
_OUTPUT_FORMATS = frozenset({"markdown"})


def _validate_export_job_data(
    producer: str,
    data: Mapping[str, object],
) -> None:
    fields = set(data)
    if producer == "reasoning":
        if not fields:
            return
        expected = {"mode", "output_format"}
        if fields != expected:
            raise ValueError(
                "reason export job hints are invalid "
                f"(missing={sorted(expected - fields)!r}, "
                f"extra={sorted(fields - expected)!r})"
            )
        mode = data["mode"]
        if not isinstance(mode, str) or mode not in _OUTPUT_MODES:
            raise ValueError("reason export job mode is invalid")
        output_format = data["output_format"]
        if (
            not isinstance(output_format, str)
            or output_format not in _OUTPUT_FORMATS
        ):
            raise ValueError("reason export job output format is invalid")
        return
    if producer == "daemon_retry":
        if fields != {"attempt"}:
            raise ValueError("reason export retry data is invalid")
        attempt = data["attempt"]
        if type(attempt) is not int or attempt < 1:
            raise ValueError(
                "reason export retry attempt must be a positive integer"
            )
        return
    if producer == "daemon_reconciliation":
        if fields:
            raise ValueError("reason export reconciliation data must be empty")
        return
    raise ValueError("reason export job producer is invalid")


REASON_OUTPUT_JOB_DEFINITION = RuntimeJobDefinition(
    name=REASON_OUTPUT_JOB_NAME,
    description="Wake the Reason output worker for a durable export manifest.",
    producers=frozenset(
        {"reasoning", "daemon_retry", "daemon_reconciliation"}
    ),
    data_validator=_validate_export_job_data,
)


def build_reason_job_definition_registry() -> JobDefinitionRegistry:
    """Build the sealed job registry consumed by Reason queue owners."""

    return build_job_definition_registry((REASON_OUTPUT_JOB_DEFINITION,))
