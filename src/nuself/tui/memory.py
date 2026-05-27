"""Readable line-oriented memory renderers."""

from __future__ import annotations

from collections.abc import Sequence
import shutil
import textwrap

from nuself.domain.memory import MemoryCandidate, MemoryEntry, MemoryEvidence
from nuself.domain.profile import ProfileItem
from nuself.domain.source import SourceDocument
from nuself.memory.repository import MemoryRelationIndexRecord
from nuself.tui.render import TerminalTheme, render_key_value_field, render_record_block, render_record_header

DEFAULT_TEXT_WIDTH = 88


def render_memory_entry_row(entry: MemoryEntry, *, index: int | None = None, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    return render_record_block(
        _record_label(theme, "memory", index=index),
        _memory_entry_fields(entry, theme=theme),
        body=_list_body(entry.title, entry.body),
    )


def render_memory_entry_detail(entry: MemoryEntry, *, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    fields = [
        *_memory_entry_fields(entry, theme=theme),
        render_key_value_field("privacy", entry.privacy),
        *_optional_fields(
            [
                ("observed_at", entry.observed_at),
                ("valid_from", entry.valid_from),
                ("valid_until", entry.valid_until),
                ("temporal_note", entry.temporal_note),
            ]
        ),
    ]
    lines = [render_record_header(_record_label(theme, "memory"), fields)]
    lines.extend(f"  {line}" for line in _detail_body_lines(entry.title, entry.body))
    lines.extend(_evidence_section(entry.evidence, theme=theme))
    return "\n".join(lines)


def render_candidate_row(candidate: MemoryCandidate, *, index: int | None = None, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    fields = [
        _state_field(theme, candidate.review_state),
        _styled_field(theme, "action", candidate.action, "35"),
        _type_field(theme, candidate.type),
        _styled_field(theme, "id", candidate.id, "90"),
        render_key_value_field("confidence", f"{candidate.confidence:.2f}"),
    ]
    return render_record_block(
        _record_label(theme, "candidate", index=index),
        fields,
        body=_list_body(candidate.title, candidate.body),
    )


def render_candidate_detail(candidate: MemoryCandidate, *, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    fields = [
        _state_field(theme, candidate.review_state),
        _styled_field(theme, "action", candidate.action, "35"),
        _type_field(theme, candidate.type),
        _styled_field(theme, "id", candidate.id, "90"),
        render_key_value_field("confidence", f"{candidate.confidence:.2f}"),
        render_key_value_field("importance", candidate.importance),
    ]
    fields.extend(_optional_fields([("target", candidate.target_entry_id), ("tags", list(candidate.tags))]))
    lines = [render_record_header(_record_label(theme, "candidate"), fields)]
    lines.extend(f"  {line}" for line in _detail_body_lines(candidate.title, candidate.body))
    lines.extend(_optional_section("reason", candidate.reason))
    lines.extend(_evidence_section(candidate.evidence, theme=theme))
    return "\n".join(lines)


def render_profile_row(item: ProfileItem, *, index: int | None = None, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    fields = [
        _type_field(theme, item.type),
        _styled_field(theme, "id", item.id, "90"),
        *_optional_fields([("tags", list(item.tags))], theme=theme),
        render_key_value_field("confidence", f"{item.confidence:.2f}"),
        render_key_value_field("importance", item.importance),
    ]
    return render_record_block(
        _record_label(theme, "profile", index=index),
        fields,
        body=_list_body(item.title, item.body),
    )


def render_profile_detail(item: ProfileItem, *, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    fields = [
        _type_field(theme, item.type),
        _styled_field(theme, "id", item.id, "90"),
        render_key_value_field("confidence", f"{item.confidence:.2f}"),
        render_key_value_field("importance", item.importance),
        render_key_value_field("privacy", item.privacy),
        *_optional_fields([("tags", list(item.tags))], theme=theme),
    ]
    lines = [render_record_header(_record_label(theme, "profile"), fields)]
    lines.extend(f"  {line}" for line in _detail_body_lines(item.title, item.body))
    lines.extend(_evidence_section(item.evidence, theme=theme))
    return "\n".join(lines)


def render_source_row(
    document: SourceDocument,
    *,
    index: int | None = None,
    chunk_count: int | None = None,
    color: bool | None = None,
) -> str:
    theme = TerminalTheme(color=color)
    fields = [
        _styled_field(theme, "id", document.id, "90"),
        *_optional_fields([("chunks", chunk_count)]),
        *_optional_fields([("tags", list(document.tags))], theme=theme),
        render_key_value_field("privacy", document.privacy),
        _styled_field(theme, "path", str(document.path), "90"),
    ]
    return render_record_block(
        _record_label(theme, "source", index=index),
        fields,
        body=document.title,
    )


def render_source_detail(document: SourceDocument, *, chunk_count: int, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    fields = [
        _styled_field(theme, "id", document.id, "90"),
        _styled_field(theme, "kind", document.kind, "36"),
        render_key_value_field("privacy", document.privacy),
        render_key_value_field("chunks", chunk_count),
        _styled_field(theme, "path", str(document.path), "90"),
        *_optional_fields([("tags", list(document.tags))], theme=theme),
        *_optional_fields([("origin", document.origin), ("source_date", document.source_date)]),
    ]
    return render_record_block(_record_label(theme, "source"), fields, body=document.title)


def render_relation_row(record: MemoryRelationIndexRecord, *, color: bool | None = None) -> str:
    theme = TerminalTheme(color=color)
    target_title = record.target_title or "(missing target)"
    return (
        f"{theme.tag('[rel]', 'persona')} {record.source_id} --{record.relation}-> {record.target_id} "
        f"conf={record.confidence:.2f} target={target_title}"
    )


def _record_label(theme: TerminalTheme, name: str, *, index: int | None = None) -> str:
    label = theme.tag(f"[{name}]", "memory")
    if index is None:
        return label
    return f"{label} [{index}]"


def _memory_entry_fields(entry: MemoryEntry, *, theme: TerminalTheme) -> list[str]:
    return [
        _state_field(theme, entry.review_state),
        _type_field(theme, entry.type),
        _styled_field(theme, "id", entry.id, "90"),
        *_optional_fields([("tags", list(entry.tags))], theme=theme),
        render_key_value_field("confidence", f"{entry.confidence:.2f}"),
    ]


def _state_field(theme: TerminalTheme, state: str) -> str:
    return f"state={_state_value(theme, state)}"


def _state_value(theme: TerminalTheme, state: str) -> str:
    if state in {"reviewed", "accepted"}:
        return theme.paint(state, "32")
    if state in {"rejected"}:
        return theme.paint(state, "31")
    if state in {"archived"}:
        return theme.paint(state, "34")
    return theme.paint(state, "33")


def _type_field(theme: TerminalTheme, value: str) -> str:
    return _styled_field(theme, "type", value, _type_color(value))


def _styled_field(theme: TerminalTheme, key: str, value: object, color_code: str) -> str:
    raw = render_key_value_field(key, value)
    field_key, separator, field_value = raw.partition("=")
    if not separator:
        return theme.paint(raw, color_code)
    return f"{field_key}={theme.paint(field_value, color_code)}"


def _type_color(value: str) -> str:
    if value in {"belief", "profile_fact", "fact"}:
        return "36"
    if value in {"preference"}:
        return "35"
    if value in {"goal"}:
        return "32"
    if value in {"concept"}:
        return "34"
    return "33"


def _optional_fields(items: Sequence[tuple[str, object | None]], *, theme: TerminalTheme | None = None) -> list[str]:
    fields: list[str] = []
    for key, value in items:
        if value is None or value == "" or value == []:
            continue
        if theme is not None and key in {"id", "path", "tags"}:
            fields.append(_styled_field(theme, key, value, "90"))
        else:
            fields.append(render_key_value_field(key, value))
    return fields


def _evidence_section(evidence_items: Sequence[MemoryEvidence], *, theme: TerminalTheme) -> list[str]:
    if not evidence_items:
        return []
    lines = ["  evidence:"]
    for evidence in evidence_items:
        summary = f"  {evidence.summary}" if evidence.summary else ""
        lines.append(theme.muted(f"    - {evidence.source_type}:{evidence.source_ref}{summary}"))
    return lines


def _optional_section(label: str, value: str | None) -> list[str]:
    if value is None or value.strip() == "":
        return []
    return [f"  {label}: {value}"]


def _list_body(title: str, body: str) -> str:
    lines = _detail_body_lines(title, body)
    return "\n".join(lines)


def _detail_body_lines(title: str, body: str) -> list[str]:
    lines: list[str] = []
    if title.strip():
        lines.extend(_wrap_body(title))
    if body.strip() and body.strip() != title.strip():
        lines.extend(_wrap_body(body))
    return lines


def _wrap_body(body: str) -> list[str]:
    width = shutil.get_terminal_size((DEFAULT_TEXT_WIDTH, 24)).columns
    return textwrap.wrap(body, width=max(min(width, DEFAULT_TEXT_WIDTH), 40)) or [""]
