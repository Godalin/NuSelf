"""Local-file ingestion adapter for Source."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from nuself.runtime.clock import utc_now_iso
from nuself.source.record import PrivacyLevel, SourceChunk, SourceDocument, SourceKind, chunk_id_for, source_id_for_path

SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt"}
CHUNK_TARGET_CHARS = 1200


def source_paths(path: Path) -> list[Path]:
    resolved = path.resolve()
    if resolved.is_file():
        if resolved.suffix.casefold() not in SUPPORTED_SUFFIXES:
            raise ValueError(f"unsupported source file type: {resolved}")
        return [resolved]
    if resolved.is_dir():
        return [item for item in sorted(resolved.rglob("*")) if item.is_file() and item.suffix.casefold() in SUPPORTED_SUFFIXES]
    raise ValueError(f"source path does not exist: {resolved}")


def load(path: Path, *, tags: list[str] | None = None, privacy: PrivacyLevel = "private") -> tuple[SourceDocument, list[SourceChunk]]:
    source_path = path.resolve()
    text = source_path.read_text(encoding="utf-8")
    kind: SourceKind = "markdown" if source_path.suffix.casefold() in {".md", ".markdown"} else "text"
    metadata, body = _parse(text, kind)
    source_id = source_id_for_path(source_path)
    title = metadata.title or _title(body, markdown=kind == "markdown") or source_path.stem
    document = SourceDocument(
        id=source_id,
        title=title,
        path=str(source_path),
        kind=kind,
        origin=metadata.origin,
        privacy=metadata.privacy or privacy,
        tags=_dedupe([*metadata.tags, *(tags or [])]),
        source_date=metadata.date,
        updated_at=utc_now_iso(),
    )
    return document, _chunks(document, body)


@dataclass(frozen=True)
class _Metadata:
    title: str = ""
    tags: tuple[str, ...] = ()
    date: str | None = None
    origin: str = "local"
    privacy: PrivacyLevel | None = None


def _parse(text: str, kind: SourceKind) -> tuple[_Metadata, str]:
    lines = text.splitlines()
    values: dict[str, str] = {}
    body_start = 0
    if lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                body_start = index + 1
                break
            if ":" in line:
                key, value = line.split(":", 1)
                values[key.strip().casefold()] = value.strip()
    raw_privacy = values.get("privacy")
    if raw_privacy not in {None, "", "private", "shareable"}:
        raise ValueError(f"unsupported source privacy: {raw_privacy}")
    raw_tags = values.get("tags", "").strip("[]")
    metadata = _Metadata(
        title=values.get("title", ""),
        tags=tuple(item.strip().strip("'\"") for item in raw_tags.split(",") if item.strip().strip("'\"")),
        date=values.get("date"),
        origin=values.get("origin", "local"),
        privacy=cast(PrivacyLevel | None, raw_privacy or None),
    )
    return metadata, "\n".join(lines[body_start:]).strip()


def _title(text: str, *, markdown: bool) -> str:
    for line in text.splitlines():
        value = line.strip()
        if markdown and value.startswith("#"):
            return value.lstrip("#").strip()
        if value:
            return value[:80]
    return ""


def _chunks(document: SourceDocument, body: str) -> list[SourceChunk]:
    values: list[str] = []
    current = ""
    for paragraph in (part.strip() for part in body.split("\n\n") if part.strip()):
        if current and len(current) + len(paragraph) + 2 > CHUNK_TARGET_CHARS:
            values.append(current)
            current = paragraph
        else:
            current = paragraph if not current else f"{current}\n\n{paragraph}"
    if current:
        values.append(current)
    return [SourceChunk(id=chunk_id_for(document.id, index), source_id=document.id, source_ref=f"source:{document.id}:{index}", index=index, text=value, title=document.title, path=document.path) for index, value in enumerate(values)]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
