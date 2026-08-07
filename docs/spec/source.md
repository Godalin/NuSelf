# Source

Status: authoritative for v0.4.0.

Source is NuSelf's external knowledge domain. It owns imported documents and
chunks from local files and future connectors such as Zotero. Source content is
not personal Memory and is never ambient Chat context.

## Boundary

Source owns normalized `SourceDocument` and `SourceChunk` records, persistence,
search, library management, deterministic local-file parsing, and connector
adaptation. Memory does not scan files, parse front matter, persist Source
records, or search Source chunks.

Chat receives a read-only Source query capability through framework-native
tools. The Agent calls `source_search`, `source_get`, or `source_list` only when
the active Source skill applies. Context preparation never queries Source.

Source does not receive MemoryCandidate or Profile repositories. Import and
delete operations cannot create or remove personal Memory/Profile records.
Future promotion of selected Source evidence into personal Memory must use the
producer-neutral `MemoryObservation` API as an explicit application use case.

## Local Ingestion

The initial local adapter accepts `.md`, `.markdown`, and `.txt` files or a
directory tree. It parses the existing `title`, `tags`, `date`, `origin`, and
`privacy` front-matter fields, normalizes a document, chunks paragraphs at the
existing target size, and asks `SourceService` to replace that document and its
chunks. Existing IDs and wire schemas remain stable.

Local paths are adapter metadata, not the identity contract for future
connectors. A future Zotero adapter supplies normalized records with stable
external identity without changing Source query or Chat tools.

## API

`SourceService` is the application API:

- `ingest_path`, `delete`, `get`, and `list` manage the library;
- `chunks`, `search`, and `get_chunk` provide typed query results;
- repositories remain internal persistence details.

`source_search` returns bounded excerpts and stable source/chunk references.
If its first result is empty, the Source skill permits exactly one distinct,
broader search. `source_get` retrieves a selected document or chunk. Tool
results remain external evidence and must not be described as user memory.
