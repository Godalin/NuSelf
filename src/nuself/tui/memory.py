"""Readable line-oriented memory renderers."""

from __future__ import annotations

from collections.abc import Sequence
import shutil
import textwrap

from nuself.domain.memory import MemoryCandidate, MemoryEntry, MemoryEvidence
from nuself.domain.profile import ProfileItem
from nuself.domain.source import SourceDocument
from nuself.memory.repository import MemoryRelationIndexRecord
from nuself.tui.render import TerminalTheme

DEFAULT_TEXT_WIDTH = 88


def render_memory_entry_row(entry: MemoryEntry, *, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    tags = _format_tags(entry.tags)
    return " ".join(
        _omit_empty(
            [
                theme.tag("[mem]", "memory"),
                _state(theme, entry.review_state),
                entry.type,
                theme.muted(entry.id),
                entry.title,
                tags,
                f"conf={entry.confidence:.2f}",
            ]
        )
    )


def render_memory_entry_detail(entry: MemoryEntry, *, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    lines = [
        f"{theme.tag('[mem]', 'memory')} {entry.title}",
        _metadata_line(
            [
                f"id={entry.id}",
                f"type={entry.type}",
                f"state={entry.review_state}",
                f"confidence={entry.confidence:.2f}",
                f"privacy={entry.privacy}",
            ],
            theme=theme,
        ),
    ]
    lines.extend(_optional_section("tags", ", ".join(entry.tags)))
    lines.extend(
        _optional_section(
            "time",
            " ".join(
                _omit_empty(
                    [
                        _field("observed", entry.observed_at),
                        _field("valid_from", entry.valid_from),
                        _field("valid_until", entry.valid_until),
                        _field("note", entry.temporal_note),
                    ]
                )
            ),
        )
    )
    lines.extend(_evidence_section(entry.evidence, theme=theme))
    lines.append("")
    lines.extend(_wrap_body(entry.body))
    return "\n".join(lines)


def render_candidate_row(candidate: MemoryCandidate, *, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    target = f"-> {candidate.target_entry_id}" if candidate.target_entry_id else ""
    return " ".join(
        _omit_empty(
            [
                theme.tag("[cand]", "memory"),
                _state(theme, candidate.review_state),
                candidate.action,
                candidate.type,
                theme.muted(candidate.id),
                target,
                candidate.title,
                _format_tags(candidate.tags),
                f"imp={candidate.importance}",
            ]
        )
    )


def render_candidate_detail(candidate: MemoryCandidate, *, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    lines = [
        f"{theme.tag('[cand]', 'memory')} {candidate.title}",
        _metadata_line(
            [
                f"id={candidate.id}",
                f"action={candidate.action}",
                f"type={candidate.type}",
                f"state={candidate.review_state}",
                f"confidence={candidate.confidence:.2f}",
                f"importance={candidate.importance}",
            ],
            theme=theme,
        ),
    ]
    lines.extend(_optional_section("target", candidate.target_entry_id))
    lines.extend(_optional_section("reason", candidate.reason))
    lines.extend(_optional_section("tags", ", ".join(candidate.tags)))
    lines.extend(_evidence_section(candidate.evidence, theme=theme))
    lines.append("")
    lines.extend(_wrap_body(candidate.body))
    return "\n".join(lines)


def render_profile_row(item: ProfileItem, *, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    return " ".join(
        _omit_empty(
            [
                theme.tag("[profile]", "chat"),
                item.type,
                theme.muted(item.id),
                item.title,
                _format_tags(item.tags),
                f"conf={item.confidence:.2f}",
                f"imp={item.importance}",
            ]
        )
    )


def render_profile_detail(item: ProfileItem, *, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    lines = [
        f"{theme.tag('[profile]', 'chat')} {item.title}",
        _metadata_line(
            [
                f"id={item.id}",
                f"type={item.type}",
                f"confidence={item.confidence:.2f}",
                f"importance={item.importance}",
                f"privacy={item.privacy}",
            ],
            theme=theme,
        ),
    ]
    lines.extend(_optional_section("tags", ", ".join(item.tags)))
    lines.extend(_evidence_section(item.evidence, theme=theme))
    lines.append("")
    lines.extend(_wrap_body(item.body))
    return "\n".join(lines)


def render_source_row(document: SourceDocument, *, chunk_count: int | None = None, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    chunks = f"chunks={chunk_count}" if chunk_count is not None else ""
    return " ".join(
        _omit_empty(
            [
                theme.tag("[src]", "outbox"),
                theme.muted(document.id),
                str(document.path),
                document.title,
                chunks,
                _format_tags(document.tags),
                document.privacy,
            ]
        )
    )


def render_source_detail(document: SourceDocument, *, chunk_count: int, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    lines = [
        f"{theme.tag('[src]', 'outbox')} {document.title}",
        _metadata_line(
            [
                f"id={document.id}",
                f"kind={document.kind}",
                f"privacy={document.privacy}",
                f"chunks={chunk_count}",
            ],
            theme=theme,
        ),
        f"path: {document.path}",
    ]
    lines.extend(_optional_section("tags", ", ".join(document.tags)))
    lines.extend(_optional_section("origin", document.origin))
    lines.extend(_optional_section("source_date", document.source_date))
    return "\n".join(lines)


def render_relation_row(record: MemoryRelationIndexRecord, *, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    target_title = record.target_title or "(missing target)"
    return (
        f"{theme.tag('[rel]', 'persona')} {record.source_id} --{record.relation}-> {record.target_id} "
        f"conf={record.confidence:.2f} target={target_title}"
    )


def _metadata_line(items: Sequence[str], *, theme: TerminalTheme) -> str:
    return theme.muted("  ".join(items))


def _evidence_section(evidence_items: Sequence[MemoryEvidence], *, theme: TerminalTheme) -> list[str]:
    if not evidence_items:
        return []
    lines = ["evidence:"]
    for evidence in evidence_items:
        summary = f"  {evidence.summary}" if evidence.summary else ""
        lines.append(theme.muted(f"  - {evidence.source_type}:{evidence.source_ref}{summary}"))
    return lines


def _optional_section(label: str, value: str | None) -> list[str]:
    if value is None or value.strip() == "":
        return []
    return [f"{label}: {value}"]


def _field(name: str, value: str | None) -> str:
    if value is None or value == "":
        return ""
    return f"{name}={value}"


def _format_tags(tags: Sequence[str]) -> str:
    return " ".join(f"#{tag}" for tag in tags)


def _state(theme: TerminalTheme, state: str) -> str:
    if state in {"reviewed", "accepted"}:
        return theme.paint(state, "32")
    if state in {"rejected"}:
        return theme.paint(state, "31")
    return theme.paint(state, "33")


def _wrap_body(body: str) -> list[str]:
    width = shutil.get_terminal_size((DEFAULT_TEXT_WIDTH, 24)).columns
    return textwrap.wrap(body, width=max(min(width, DEFAULT_TEXT_WIDTH), 40)) or [""]


def _omit_empty(items: Sequence[str]) -> list[str]:
    return [item for item in items if item != ""]
