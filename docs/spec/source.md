# Source

Status: authoritative for v0.4.0.

Source is NuSelf's external knowledge domain. It owns imported documents and
chunks from local files and future connectors such as Zotero. Source content is
not personal Memory and is never ambient Chat context.

## Boundary

Source owns normalized immutable `SourceDocument` and `SourceChunk` revisions,
persistence, search, append-only ingestion, deterministic local-file parsing,
and connector adaptation. Memory does not scan files, parse front matter,
persist Source records, or search Source chunks.

Chat receives a read-only Source query capability through framework-native
tools. The Agent calls `source_search`, `source_get`, or `source_list` only when
the active Source skill applies. Context preparation never queries Source.

Source does not receive MemoryCandidate or Profile repositories. Import
operations cannot create or remove personal Memory/Profile records.
Future promotion of selected Source evidence into personal Memory must use the
producer-neutral `MemoryObservation` API as an explicit application use case.

## Local Ingestion

The initial local adapter accepts `.md`, `.markdown`, and `.txt` files or a
directory tree. It parses the existing `title`, `tags`, `date`, `origin`, and
`privacy` front-matter fields, normalizes a document, chunks paragraphs at the
existing target size, and asks `SourceImporter` to append that document revision
and its chunks in one storage transaction. `SourceService` remains query-only.

Revision identity includes connector identity plus normalized imported content
and import options. Reimporting the same revision is idempotent. Changed
content creates a new document ID and stable chunk references; it never
rewrites the earlier revision. Existing persisted IDs and wire schemas remain
readable. Source exposes no delete operation; generic authority backup and
administration remain separate from the Source domain API.

Local paths are adapter metadata, not the identity contract for future
connectors. A future Zotero adapter supplies normalized records with stable
external identity without changing Source query or Chat tools.

## API

`SourceService` is the read-only application and Agent API:

- `get`, `list`, `chunks`, `search`, and `get_chunk` provide typed query
  results;
- repositories remain internal persistence details.

`SourceImporter` is the explicit CLI/connector ingestion capability. It can
append immutable revisions but cannot update or delete an existing revision.

`source_search` returns bounded excerpts and stable source/chunk references.
If its first result is empty, the Source skill permits exactly one distinct,
broader search. `source_get` retrieves a selected document or chunk. Tool
results remain external evidence and must not be described as user memory.
