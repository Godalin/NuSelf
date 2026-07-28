# Memory Spec

## Intake Flow

### Manual Addition (`memory add`)

1. If both `--type` and `--title` are provided explicitly, skip LLM inference.
2. Otherwise, `MemoryIntakeAgent.infer()` calls the LLM.
3. On LLM failure or invalid JSON, the command fails. Manual memory addition must not synthesize a local heuristic fallback entry.
4. The agent must normalize body by collapsing whitespace.
5. The agent must raise `ValueError` if normalized body is empty.
6. The agent must include up to 5 matching profile items in the LLM prompt.
7. The LLM result must include `type`, `title`, `tags`, `confidence`, and `importance`.
8. Result is written directly to `MemoryEntryRepository` (bypasses candidate queue), then `reindex()` is called.

## Temporal Memory Contract

Memory records carry two different kinds of time:

- `created_at`: when NuSelf wrote the memory record.
- `updated_at`: when NuSelf last changed the memory record.
- `observed_at`: when the remembered fact, preference, question, or episode was observed in conversation or source material.
- `valid_from` / `valid_until`: the semantic validity window of the remembered content when known.
- `temporal_note`: a short human-readable note explaining temporal uncertainty or evolution.

Rules:

- Runtime storage keeps timestamps as timezone-aware ISO strings.
- `created_at` and `updated_at` are storage metadata; they do not necessarily describe when the remembered thing happened.
- `observed_at` should be filled when the source has an event/date or when a chat-derived memory is created from a thread turn.
- For chat-derived memories, `observed_at` should use the curation source time and evidence should carry the same observation time.
- Retrieval context shown to chat must include available temporal fields so NuSelf can reason about whether a memory is old, recent, current, or historically bounded.
- Missing temporal fields must be omitted from compact prompts rather than rendered as `None`.

## Read-Model Collection Ownership

`MemoryEntry`, `MemoryCandidate`, `MemoryObject`, `ProfileItem`, and
`SourceDocument` are immutable persisted read models. They must not retain
aliases to caller-owned containers. Construction and wire decoding recursively
freeze tags, source references, relations, payload, metadata, and collection
membership around immutable `MemoryEvidence` records.

The persisted wire contract remains ordinary JSON lists and objects.
`to_wire()` returns a recursively detached mutable-container tree; mutating
that result must not affect the model or a later serialization. Descriptor
validation, merge, conversion, retrieval, and relation traversal must accept
the immutable in-memory `Mapping` and `Sequence` forms without weakening their
existing wire-shape validation.

### Source Ingestion (`source ingest`)

1. Accept single `.md`/`.txt` files or recurse into directories.
2. Parse YAML front matter (`title`, `tags`, `date`, `origin`, `privacy`).
3. Chunk by paragraphs targeting ~1200 chars per chunk.
4. Write one `SourceDocument` and per-chunk `SourceChunk` files under `private/sources/`.
5. No candidates created automatically.

### Source Extraction (`source extract`)

1. Create one `MemoryCandidate` per chunk with `action="create"`, `type="profile_fact"`.
2. Deterministic ID: `cand_<uuid5(source_ref)>`.
3. Save to `MemoryCandidateRepository` for manual review.

### Validation Gates on Save

- `MemoryEntryRepository.save()`:
  - Unknown type + `review_state=="draft"` → quarantine to `review_state="quarantined"`.
  - Unknown type + `review_state!="draft"` → raise `MemoryValidationError`.
  - Otherwise, call `MemoryTypeDescriptor.validate()`; if issues exist, raise `MemoryValidationError`.
- `MemoryCandidateRepository.save()` performs **no** descriptor validation.

## Curation Flow (`MemoryCurator`)

### Triggers

1. Daemon background thread every `daemon.memory_curator.interval_seconds` (default `300`).
2. After every daemon chat turn.
3. Manual CLI: `nuself memory update`.

Post-chat curation is a secondary effect after the assistant reply has already
been produced and persisted. A declared recoverable `RuntimeError` must not
replace that reply: the daemon returns it with no `memory_update` and emits
`memory/post_chat_curation_failed` through the shared observability boundary.
The event inherits the chat request, thread, turn, and source context and
preserves the compact exception chain. Undeclared storage or implementation
errors are not degraded and continue to the daemon request backstop.

### Per-Thread Cursor

- Load cursor from `private/memory/cursors/{thread_id}.json`.
- A missing cursor means the thread has not been processed and starts at zero.
- A present cursor is an authoritative typed record containing the same
  `thread_id` as its filename/request and a non-negative integer
  `processed_message_count`.
- Invalid JSON, non-object shape, mismatched identity, boolean/non-integer
  counts, and negative counts are corrupt state. The curator reports a
  payload-safe `record_decode_failed` event and aborts that run; it must not
  reinterpret corruption as cursor zero and replay old messages.
- Cursor updates use atomic same-directory replacement.
- If `cursor >= next_message_index`, no-op (idempotent).
- If thread was compressed (`cursor < message_start_index`), log gap and start from `visible_start`.
- Advance cursor to `visible_end` after processing.

### Quality Gate (`_has_memory_worthy_signal`)

- Inspect only `role=="user"` messages.
- If concatenated user text `< 120` chars AND contains none of the durable markers (`prefer`, `remember`, `important`, `decide`, `decision`, `should`, `goal`, `plan`, `because`, `why`, `question`, `always`, `never`), return `processed_messages=0` without LLM call.

### Curator LLM Decision Contract

- Must return JSON with `actions` array. Allowed actions: `create`, `update`, `ignore`.
- `create` and `update` actions must include `tags`: a non-empty list of short strings. Tags are part of the durable memory handle surface and must be copied to `MemoryCandidate` and any accepted `MemoryEntry`.
- Action parsing is a typed boundary: JSON is parsed into the structured curator action schema, then converted to `MemoryAction`. The curator must not keep a parallel hand-written dict parser or coerce unknown memory types to a fallback type.
- On LLM failure or invalid JSON → defer (status `deferred`).
- `create`/`update` actions with empty `title`/`body`, empty `tags`, unknown `type`, or raw-transcript bodies (`>=2` occurrences of `user:`/`assistant:`) → discarded.
- LLM prompt includes: thread summary, up to 12 existing memory entries, up to 12 profile items, and the current registered memory type names from `MemoryTypeRegistry`.

### Conflict Detection

- Before creating, check `MemoryTypeRegistry.conflicts(existing, incoming)` against up to 12 existing entries.
- If conflict → call `registry.merge(existing, incoming)` and produce `action="update"` candidate with `target_entry_id=existing.id`.
- If no conflict → produce `action="create"` candidate.

### Auto-Accept

- `MemoryCuratorSettings.auto_accept` defaults to `True`.
- When `auto_accept=True`, immediately call `accept(candidate.id)` after saving.
  - For `create`/`update`/`merge`: produces `MemoryEntry`, then overwrites `review_state="reviewed"`.
  - Validation or not-found failures retain the already-durable candidate as
    `pending`, emit `memory/auto_accept_failed` with its identity and compact
    exception chain, and allow the curator cursor to advance so the same source
    turn is not converted into another candidate.
  - Undeclared storage or implementation failures propagate and prevent cursor
    advance; auto-accept must not broadly suppress a potentially partial write.
- When `auto_accept=False`, candidates remain `pending`.

## Optimization Flow (`MemoryOptimizer`)

### Trigger

- **Only manual CLI**: `nuself memory optimize --limit N`.
- No daemon background thread.

### Scope

- Load up to `memory_limit` (default `50`) most recently updated entries.
- Empty repository → return `reviewed=0`.

### Optimizer LLM Decision Contract

- Must return JSON with `actions` array. Allowed: `update`, `delete`, `ignore`.
- On failure → defer.
- Update actions with empty `title`/`body` or raw-transcript bodies → rejected.
- Delete actions missing `entry_id` → ignored.

### Update Path

1. Load existing entry.
2. Build `incoming MemoryObject` from action fields.
3. Call `MemoryTypeRegistry.merge(existing, incoming)`.
4. Create candidate with `action="update"`, `target_entry_id=existing.id`.

### Delete Path

1. Create candidate with `action="delete"`, `target_entry_id=existing.id`.
2. Actual deletion happens only upon acceptance.

### No Auto-Accept

Optimizer candidates remain `pending` for manual review.

## Candidate Review Queue

### States

| State | Meaning | Final? |
|---|---|---|
| `pending` | Awaiting decision | No |
| `accepted` | Committed to durable memory | Yes |
| `rejected` | Discarded | Yes |

### Transitions

- **Accept `create`**: Converts to `MemoryEntry` (or `ProfileItem`) with `review_state="draft"`; curator auto-accept overwrites to `reviewed`.
- **Accept `update`/`merge`**: Requires `target_entry_id`. Merges fields into target, preserving `id`/`created_at`, updating `updated_at`. Source refs and evidence concatenated; relations deduplicated.
- **Accept `delete`**: Requires `target_entry_id`. Deletes target from repository.
- **Reject**: Flips `review_state` to `rejected`.
- **Edit**: Updates any subset of `title`, `body`, `tags`, `importance`, temporal fields.

### Entry Review States

| State | Meaning |
|---|---|
| `draft` | Newly created, not yet reviewed |
| `reviewed` | Accepted and durable |
| `quarantined` | Unknown type, awaiting recovery |
| `rejected` | Explicitly rejected |

## Query / Retrieval (`MemoryQueryService`)

### Filtering Before Scoring

- `review_state` in query's `review_states` (default `("draft", "reviewed")`).
- `memory_types` filter: if non-empty, entry type must match.
- `tags` filter: if non-empty, entry must contain **all** query tags (case-insensitive).
- `MemoryTypeRegistry.retrieve(entry.type, query.text, query.limit)` must return `True`.
- `min_importance`: entry importance must be `>=` it.

### Scoring Function

| Signal | Bonus | Reason |
|---|---|---|
| Full query in title | `+5.0` | `title_phrase` |
| Full query in body | `+3.0` | `body_phrase` |
| Full query in tags | `+4.0` | `tag_phrase` |
| Token in title | `+3.0` | `title` |
| Token in tags | `+2.5` | `tag` |
| Token in body | `+1.0` | `body` |
| Type affinity match | up to `+3.0` | `type_descriptor` |
| `reviewed` state | `+0.5` | — |
| Confidence | `+min(conf,1.0) * 0.25` | — |
| Importance | `+min(imp,1.0) * 0.5` | — |

Entries with `score <= 0` excluded.

### Relation Expansion

- Direct matches sorted by `(-score, updated_at, id)`, capped at `limit`.
- If direct matches `< limit`, expand via:
  1. **Outgoing relations**: targets in `entry.relations[descriptor.source_field]`.
  2. **Incoming relations**: other entries whose relations list contains this entry.
  3. **Transitive closure**: for `transitive=True` relations, indirect neighbors.
- Score penalties for related matches:
  - `include_both_current_and_superseded`: `-0.5`
  - `include_direct_neighbors` (default): `-0.75`
  - Transitive closure extra: `-0.25`
  - Minimum related score: `0.1`
- Multi-path: highest score wins, reasons concatenated.

## Type System (`MemoryTypeDescriptor`)

### Required Hooks

| Hook | Signature | Purpose |
|---|---|---|
| `validate` | `(MemoryObject) -> list[MemoryValidationIssue]` | Structural validation |
| `summarize` | `(MemoryObject) -> str` | Human-readable summary |
| `merge` | `(existing, incoming) -> MemoryObject` | Combine two memories |
| `conflicts` | `(a, b) -> bool` | Whether two memories collide |
| `decay` | `(memory, now) -> MemoryObject \| None` | Time-based degradation; `None` = remove |
| `retrieve` | `(query, budget) -> bool` | Whether type is relevant to query |
| `reflect` | `(memory, context) -> list[MemoryObject]` | Generate derived candidates |
| `example` | `() -> MemoryObject` | Representative instance |
| `importance` | `(memory) -> float` | Override or confirm importance (0–1) |

### Built-In Types

| Type | Default Importance | Conflict Rule |
|---|---|---|
| `source_note` | `0.4` | Matching title (case-insensitive, stripped) |
| `profile_fact` | `0.9` | Matching title |
| `belief` | `0.7` | Matching title |
| `preference` | `0.6` | Matching title |
| `goal` | `0.8` | Matching title |
| `concept` | `0.5` | Matching title |
| `style_trait` | `0.5` | Matching title |
| `episode` | `0.4` | Matching title |
| `open_question` | `0.3` | Matching title |
| `instruction` | `0.6` | Matching title |
| `persona_instruction` | `0.9` | Matching `persona_id` |

### Unknown-Type Fallback

- Validation: allowed only if `review_state=="draft"`; otherwise raises `MemoryValidationError`.
- Save: auto-quarantined.
- Merge: `_default_merge` (incoming wins, existing id preserved).
- Conflicts: `_default_conflicts` (only same id).
- Decay: unchanged.
- Retrieve: always `True`.
- Reflect: empty list.
- Importance: falls back to `memory.importance`.

## Symbolic Graph

### Built-In Relations

| Name | Inverse | Symmetric | Transitive | Retrieval Rule | Temporal Policy |
|---|---|---|---|---|---|
| `supersedes` | `superseded_by` | No | No | `include_both_current_and_superseded` | `source_validity_refines_target` |
| `related_to` | `related_to` | Yes | No | `include_direct_neighbors` | `independent` |
| `supports` | `supported_by` | No | No | `include_direct_neighbors` | `independent` |
| `contradicts` | `contradicted_by` | No | No | `include_direct_neighbors` | `independent` |
| `refines` | `refined_by` | No | No | `include_direct_neighbors` | `source_validity_refines_target` |
| `depends_on` | `required_by` | No | Yes | `include_direct_neighbors` | `independent` |

### Derived Graph Contract

- Graph is **derived and rebuildable**, not authoritative.
- `reindex()` writes `private/derived/symbolic_graph.json` and `private/derived/relation_index.json`.
- Nodes are memory entries; edges generated from `entry.relations`.
- Edge IDs are deterministic: `{source_id}:{relation}:{target_id}`.

### Graph Operations

- `search_graph(query, node_type, limit, depth)`: text-match nodes, traverse adjacency up to `depth`, respect symmetry.
- `find_path(from_id, to_id)`: BFS shortest path with symmetry.
- `transitive_closure(node_id, relation)`: BFS along single relation name; respects symmetry.
