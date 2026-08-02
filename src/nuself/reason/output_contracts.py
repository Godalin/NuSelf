"""Durable contracts and strict wire codecs for reason output."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence, TypeVar, cast

from nuself.clock import utc_now_iso
from nuself.reason.model import ReasoningStep, ReasoningThread

REASON_OUTPUT_STORAGE_VERSION = "NuSelfReasonOutput/v1"
REASON_OUTPUT_MODES: tuple[str, ...] = ("outline", "narrative", "report", "summary")
REASON_OUTPUT_FORMATS: tuple[str, ...] = ("markdown",)
REASON_OUTPUT_STATUSES: tuple[str, ...] = ("planned", "complete", "failed")
REASON_OUTPUT_PDF_STATUSES: tuple[str, ...] = (
    "pending",
    "generated",
    "failed",
)
_SECTION_FIELDS = frozenset(
    {
        "index",
        "title",
        "focus",
        "step_ids",
        "source_start_index",
        "source_end_index",
        "summary",
        "created_at",
    }
)
_CHUNK_FIELDS = frozenset(
    {"index", "filename", "step_ids", "created_at"}
)
_MANIFEST_FIELDS = frozenset(
    {
        "schema",
        "job_id",
        "thread_id",
        "mode",
        "output_format",
        "source_start_index",
        "source_end_index",
        "source_step_ids",
        "segment_size",
        "status",
        "combined_filename",
        "progress_filename",
        "created_at",
        "updated_at",
        "sections",
        "chunks",
        "attempts",
        "last_error",
        "last_attempt_at",
    }
)
_PROGRESS_FIELDS = frozenset(
    {
        "job_id",
        "thread_id",
        "status",
        "completed_chunks",
        "total_chunks",
        "pdf_status",
        "pdf_path",
        "updated_at",
    }
)
_DecodedRecord = TypeVar("_DecodedRecord")

@dataclass(frozen=True)
class ReasonOutputSection:
    index: int
    title: str
    focus: str
    step_ids: tuple[str, ...]
    source_start_index: int
    source_end_index: int
    summary: str
    created_at: str = field(default_factory=utc_now_iso)

    def to_wire(self) -> dict[str, object]:
        return {
            "index": self.index,
            "title": self.title,
            "focus": self.focus,
            "step_ids": list(self.step_ids),
            "source_start_index": self.source_start_index,
            "source_end_index": self.source_end_index,
            "summary": self.summary,
            "created_at": self.created_at,
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> ReasonOutputSection:
        _expect_exact_fields(data, _SECTION_FIELDS, label="reason output section")
        return cls(
            index=_expect_int(data, "index"),
            title=_expect_nonblank_str(data, "title"),
            focus=_expect_nonblank_str(data, "focus"),
            step_ids=_expect_str_tuple(data, "step_ids"),
            source_start_index=_expect_int(data, "source_start_index"),
            source_end_index=_expect_int(data, "source_end_index"),
            summary=_expect_str(data, "summary"),
            created_at=_expect_aware_iso(data, "created_at"),
        )


SectionPlanner = Callable[
    [ReasoningThread, Sequence[ReasoningStep], str],
    tuple[ReasonOutputSection, ...],
]


@dataclass(frozen=True)
class ReasonOutputChunk:
    index: int
    filename: str
    step_ids: tuple[str, ...]
    created_at: str = field(default_factory=utc_now_iso)

    def to_wire(self) -> dict[str, object]:
        return {
            "index": self.index,
            "filename": self.filename,
            "step_ids": list(self.step_ids),
            "created_at": self.created_at,
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> ReasonOutputChunk:
        _expect_exact_fields(data, _CHUNK_FIELDS, label="reason output chunk")
        return cls(
            index=_expect_int(data, "index"),
            filename=_expect_nonblank_str(data, "filename"),
            step_ids=_expect_str_tuple(data, "step_ids"),
            created_at=_expect_aware_iso(data, "created_at"),
        )


@dataclass(frozen=True)
class ReasonOutputManifest:
    job_id: str
    thread_id: str
    mode: str
    output_format: str
    source_start_index: int
    source_end_index: int | None
    source_step_ids: tuple[str, ...]
    segment_size: int
    status: str = "planned"
    combined_filename: str = "combined.md"
    progress_filename: str = "progress.json"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    sections: tuple[ReasonOutputSection, ...] = ()
    chunks: tuple[ReasonOutputChunk, ...] = ()
    attempts: int = 0
    last_error: str | None = None
    last_attempt_at: str | None = None

    def to_wire(self) -> dict[str, object]:
        return {
            "schema": REASON_OUTPUT_STORAGE_VERSION,
            "job_id": self.job_id,
            "thread_id": self.thread_id,
            "mode": self.mode,
            "output_format": self.output_format,
            "source_start_index": self.source_start_index,
            "source_end_index": self.source_end_index,
            "source_step_ids": list(self.source_step_ids),
            "segment_size": self.segment_size,
            "status": self.status,
            "combined_filename": self.combined_filename,
            "progress_filename": self.progress_filename,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "sections": [section.to_wire() for section in self.sections],
            "chunks": [chunk.to_wire() for chunk in self.chunks],
            "attempts": self.attempts,
            "last_error": self.last_error,
            "last_attempt_at": self.last_attempt_at,
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> ReasonOutputManifest:
        _expect_exact_fields(data, _MANIFEST_FIELDS, label="reason output manifest")
        schema = _expect_str(data, "schema")
        if schema != REASON_OUTPUT_STORAGE_VERSION:
            raise ValueError("reason output manifest schema is unsupported")
        mode = _expect_str(data, "mode")
        if mode not in REASON_OUTPUT_MODES:
            raise ValueError("reason output manifest mode is invalid")
        output_format = _expect_str(data, "output_format")
        if output_format not in REASON_OUTPUT_FORMATS:
            raise ValueError("reason output manifest output format is invalid")
        status = _expect_str(data, "status")
        if status not in REASON_OUTPUT_STATUSES:
            raise ValueError("reason output manifest status is invalid")
        source_start_index = _expect_int(data, "source_start_index")
        source_end_index = _optional_int(data, "source_end_index")
        segment_size = _expect_int(data, "segment_size")
        attempts = _expect_int(data, "attempts")
        if source_start_index < 0:
            raise ValueError("source_start_index must be non-negative")
        if source_end_index is not None and source_end_index < source_start_index:
            raise ValueError("source_end_index must not precede source_start_index")
        if segment_size < 1:
            raise ValueError("segment_size must be positive")
        if attempts < 0:
            raise ValueError("attempts must be non-negative")
        return cls(
            job_id=_expect_nonblank_str(data, "job_id"),
            thread_id=_expect_nonblank_str(data, "thread_id"),
            mode=mode,
            output_format=output_format,
            source_start_index=source_start_index,
            source_end_index=source_end_index,
            source_step_ids=_expect_str_tuple(data, "source_step_ids"),
            segment_size=segment_size,
            status=status,
            combined_filename=_expect_nonblank_str(
                data,
                "combined_filename",
            ),
            progress_filename=_expect_nonblank_str(
                data,
                "progress_filename",
            ),
            created_at=_expect_aware_iso(data, "created_at"),
            updated_at=_expect_aware_iso(data, "updated_at"),
            sections=_expect_object_tuple(
                data,
                "sections",
                ReasonOutputSection.from_wire,
            ),
            chunks=_expect_object_tuple(
                data,
                "chunks",
                ReasonOutputChunk.from_wire,
            ),
            attempts=attempts,
            last_error=_optional_str(data, "last_error"),
            last_attempt_at=_optional_aware_iso(data, "last_attempt_at"),
        )

    def with_updates(
        self,
        *,
        status: str | None = None,
        chunks: tuple[ReasonOutputChunk, ...] | None = None,
        sections: tuple[ReasonOutputSection, ...] | None = None,
        attempts: int | None = None,
        last_error: str | None = None,
        last_attempt_at: str | None = None,
    ) -> ReasonOutputManifest:
        kw: dict[str, object] = {"updated_at": utc_now_iso()}
        if status is not None:
            kw["status"] = status
        if chunks is not None:
            kw["chunks"] = chunks
        if sections is not None:
            kw["sections"] = sections
        if attempts is not None:
            kw["attempts"] = attempts
        if last_error is not None:
            kw["last_error"] = last_error
        if last_attempt_at is not None:
            kw["last_attempt_at"] = last_attempt_at
        return replace(self, **kw)  # pyright: ignore[reportArgumentType]


@dataclass(frozen=True)
class ReasonOutputProgress:
    job_id: str
    thread_id: str
    status: str
    completed_chunks: tuple[int, ...]
    total_chunks: int
    pdf_status: str
    pdf_path: str | None
    updated_at: str

    def to_wire(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "thread_id": self.thread_id,
            "status": self.status,
            "completed_chunks": list(self.completed_chunks),
            "total_chunks": self.total_chunks,
            "pdf_status": self.pdf_status,
            "pdf_path": self.pdf_path,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> ReasonOutputProgress:
        _expect_exact_fields(data, _PROGRESS_FIELDS, label="reason output progress")
        status = _expect_str(data, "status")
        if status not in REASON_OUTPUT_STATUSES:
            raise ValueError("reason output progress status is invalid")
        pdf_status = _expect_str(data, "pdf_status")
        if pdf_status not in REASON_OUTPUT_PDF_STATUSES:
            raise ValueError("reason output progress PDF status is invalid")
        total_chunks = _expect_int(data, "total_chunks")
        if total_chunks < 0:
            raise ValueError("total_chunks must be non-negative")
        completed_chunks = _expect_int_tuple(data, "completed_chunks")
        if len(set(completed_chunks)) != len(completed_chunks):
            raise ValueError("completed_chunks must not contain duplicates")
        if any(index < 0 or index >= total_chunks for index in completed_chunks):
            raise ValueError(
                "completed_chunks indexes must be within total_chunks"
            )
        return cls(
            job_id=_expect_nonblank_str(data, "job_id"),
            thread_id=_expect_nonblank_str(data, "thread_id"),
            status=status,
            completed_chunks=completed_chunks,
            total_chunks=total_chunks,
            pdf_status=pdf_status,
            pdf_path=_optional_str(data, "pdf_path"),
            updated_at=_expect_aware_iso(data, "updated_at"),
        )


@dataclass(frozen=True)
class ReasonOutputPaths:
    root: Path
    manifest: Path
    progress: Path
    combined: Path
    pdf: Path
    chunks_dir: Path


def _expect_str(data: dict[str, object], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"field '{field_name}' must be a string")
    return value


def _expect_nonblank_str(
    data: dict[str, object],
    field_name: str,
) -> str:
    value = _expect_str(data, field_name)
    if not value.strip():
        raise ValueError(f"field '{field_name}' must not be blank")
    return value


def _optional_str(data: dict[str, object], field_name: str) -> str | None:
    value = data.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"field '{field_name}' must be a string or null")
    return value


def _expect_list(data: dict[str, object], field_name: str) -> list[object]:
    value = data.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"field '{field_name}' must be a list")
    return cast(list[object], value)


def _expect_int(data: dict[str, object], field_name: str) -> int:
    value = data.get(field_name)
    if type(value) is not int:
        raise ValueError(f"field '{field_name}' must be an integer")
    return value


def _optional_int(data: dict[str, object], field_name: str) -> int | None:
    value = data.get(field_name)
    if value is None:
        return None
    if type(value) is not int:
        raise ValueError(f"field '{field_name}' must be an integer or null")
    return value


def _expect_exact_fields(
    data: dict[str, object],
    fields: frozenset[str],
    *,
    label: str,
) -> None:
    present = set(data)
    missing = sorted(fields - present)
    unknown = sorted(present - fields)
    if missing or unknown:
        raise ValueError(
            f"{label} fields are invalid "
            f"(missing={missing!r}, unknown={unknown!r})"
        )


def _expect_str_tuple(
    data: dict[str, object],
    field_name: str,
) -> tuple[str, ...]:
    values = _expect_list(data, field_name)
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"field '{field_name}' must contain non-blank strings"
            )
        result.append(value)
    return tuple(result)


def _expect_int_tuple(
    data: dict[str, object],
    field_name: str,
) -> tuple[int, ...]:
    result: list[int] = []
    for value in _expect_list(data, field_name):
        if type(value) is not int:
            raise ValueError(
                f"field '{field_name}' must contain integers"
            )
        result.append(value)
    return tuple(result)


def _expect_object_tuple(
    data: dict[str, object],
    field_name: str,
    decoder: Callable[[dict[str, object]], _DecodedRecord],
) -> tuple[_DecodedRecord, ...]:
    decoded: list[_DecodedRecord] = []
    for value in _expect_list(data, field_name):
        if not isinstance(value, dict):
            raise ValueError(
                f"field '{field_name}' must contain objects"
            )
        decoded.append(
            decoder(cast(dict[str, object], value))
        )
    return tuple(decoded)


def _expect_aware_iso(
    data: dict[str, object],
    field_name: str,
) -> str:
    value = _expect_nonblank_str(data, field_name)
    _parse_aware_iso(value, field_name=field_name)
    return value


def _optional_aware_iso(
    data: dict[str, object],
    field_name: str,
) -> str | None:
    value = _optional_str(data, field_name)
    if value is not None:
        _parse_aware_iso(value, field_name=field_name)
    return value


def _parse_aware_iso(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"field '{field_name}' must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"field '{field_name}' must include a timezone")
    return parsed
