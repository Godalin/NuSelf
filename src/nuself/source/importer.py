"""Append-only Source ingestion capability."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nuself.source import local
from nuself.source.record import PrivacyLevel
from nuself.source.repository import SourceRepository


@dataclass(frozen=True)
class SourceIngestResult:
    documents: int
    chunks: int
    unchanged: int = 0

    def summary(self) -> str:
        return (
            f"documents={self.documents} chunks={self.chunks} "
            f"unchanged={self.unchanged}"
        )


class SourceImporter:
    """Append immutable normalized revisions from external adapters."""

    def __init__(self, repository: SourceRepository) -> None:
        self._repository = repository

    def ingest(
        self,
        path: Path,
        *,
        tags: list[str] | None = None,
        privacy: PrivacyLevel = "private",
    ) -> SourceIngestResult:
        document_count = 0
        chunk_count = 0
        unchanged = 0
        for source_path in local.source_paths(path):
            document, chunks = local.load(
                source_path,
                tags=tags,
                privacy=privacy,
            )
            if not self._repository.add(document, chunks):
                unchanged += 1
                continue
            document_count += 1
            chunk_count += len(chunks)
        return SourceIngestResult(document_count, chunk_count, unchanged)
