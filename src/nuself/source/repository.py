"""Persistence for imported source documents and chunks."""

from __future__ import annotations

from nuself.config.settings import RuntimePaths
from nuself.runtime.observability import decode_observed_record
from nuself.source.record import SourceChunk, SourceDocument
from nuself.storage.contract import StorageBackend


class SourceDocumentNotFound(KeyError):
    """Raised when a source document does not exist."""


class SourceChunkNotFound(KeyError):
    """Raised when a source chunk does not exist."""


class SourceRepository:
    """Persist Source records without depending on another domain."""

    def __init__(self, paths: RuntimePaths, *, backend: StorageBackend) -> None:
        self._documents = backend.collection("source_documents")
        self._chunks = backend.collection("source_chunks")
        self._paths = paths

    def replace(self, document: SourceDocument, chunks: list[SourceChunk]) -> None:
        self._documents.put(document.id, document.to_wire())
        self._delete_chunks(document.id)
        for chunk in chunks:
            self._chunks.put(chunk.id, chunk.to_wire())

    def get_document(self, source_id: str) -> SourceDocument:
        wire = self._documents.get(source_id)
        if wire is None:
            raise SourceDocumentNotFound(source_id)
        return SourceDocument.from_wire(wire)

    def get_chunk(self, chunk_id: str) -> SourceChunk:
        wire = self._chunks.get(chunk_id)
        if wire is None:
            raise SourceChunkNotFound(chunk_id)
        return SourceChunk.from_wire(wire)

    def delete_document(self, source_id: str) -> None:
        document = self.get_document(source_id)
        self._documents.delete(document.id)
        self._delete_chunks(source_id)

    def list_documents(self) -> list[SourceDocument]:
        items: list[SourceDocument] = []
        for wire in self._documents.list():
            document = decode_observed_record(
                wire,
                SourceDocument.from_wire,
                component="memory",
                collection="source_documents",
                project_root=self._paths.authority_root,
            )
            if document is not None:
                items.append(document)
        return sorted(items, key=lambda item: item.updated_at, reverse=True)

    def list_chunks(self, source_id: str | None = None) -> list[SourceChunk]:
        items: list[SourceChunk] = []
        for wire in self._chunks.list():
            chunk = self._decode_chunk(wire)
            if chunk is not None and (source_id is None or chunk.source_id == source_id):
                items.append(chunk)
        return sorted(items, key=lambda item: (item.source_id, item.index))

    def _delete_chunks(self, source_id: str) -> None:
        for wire in self._chunks.list():
            chunk = self._decode_chunk(wire)
            if chunk is not None and chunk.source_id == source_id:
                self._chunks.delete(chunk.id)

    def _decode_chunk(self, wire: dict[str, object]) -> SourceChunk | None:
        return decode_observed_record(
            wire,
            SourceChunk.from_wire,
            component="memory",
            collection="source_chunks",
            project_root=self._paths.authority_root,
        )
