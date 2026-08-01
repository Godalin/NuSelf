# Memory Spec

## Intake Flow

### Manual Addition (`memory add`)

1. If both `--type` and `--title` are provided explicitly, skip LLM inference.
2. Otherwise, `MemoryIntakeAgent.infer()` invokes the shared framework-native
   structured-agent runner with the strict intake response model.
3. The runner must return an actual typed intake response from LangChain
   `structured_response`. Missing or dictionary-shaped structured state,
   model failure, or schema failure makes the command fail. Manual memory
   addition must not parse response text or synthesize a local heuristic
   fallback entry.
4. The agent must normalize body by collapsing whitespace.
5. The agent must raise `ValueError` if normalized body is empty.
6. The agent must include up to 5 matching profile items in the LLM prompt.
7. The LLM result must include `type`, `title`, `tags`, `confidence`, and
   `importance`. Its schema uses strict types, forbids unknown fields, requires
   1-4 tags, and constrains confidence and importance from zero through one.
   Invalid values are rejected rather than defaulted, coerced, or clamped.
   Persisted `importance=0.0` is a valid explicit value and must round-trip
   unchanged for entries, candidates, and generic memory objects. Defaults
   apply only when the field is absent, never because a numeric value is
   falsy; booleans remain invalid.
8. The generated type must be registered and the normalized title and tags
   must remain non-empty.
9. Result is written directly to `MemoryEntryRepository` (bypasses candidate
   queue); SQLite is immediately authoritative and no sidecar index is written.

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
- `observed_at` should be filled when the source has an event/date or when a chat-derived memory is created from a conversation turn.
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
Required and optional string fields share one codec each across concrete dict
records and abstract mapping payloads. Container annotation differences must
not create duplicate validators with identical accepted values and errors.

`relations` is the only persisted relation field for memory entries,
candidates, profile items, and the entry payload embedded in `MemoryObject`.
Relation names map to lists of target memory ids. The obsolete top-level and
payload fields `supersedes` and `related_memory_ids` are neither written nor
decoded; records using those shapes require an explicit storage migration
before they can be loaded.

Repository statistics results follow the same read-ownership principle.
`MemoryStats` and `ProfileStats` detach and freeze their mapping fields during
construction. A caller may retain or inspect a statistics snapshot but cannot
mutate an apparently frozen result or alter the dictionaries supplied by the
repository while composing that snapshot.

### Source Ingestion (`source ingest`)

1. Accept single `.md`/`.txt` files or recurse into directories.
2. Parse YAML front matter (`title`, `tags`, `date`, `origin`, `privacy`).
3. Chunk by paragraphs targeting ~1200 chars per chunk.
4. Write one `SourceDocument` and per-chunk `SourceChunk` files under `<authority-root>/sources/`.
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

1. After committing a reply, the conversation boundary selects the completed
   turn and calls the generic memory `observe()` API. The API durably stores a
   producer-neutral observation before curation is requested.
2. The daemon's unified scheduler coalesces observation IDs and processes them
   promptly. Every `daemon.memory_curator.interval_seconds` (default `300`) it
   scans the memory-owned pending observation inbox. It never scans
   conversation storage.
3. Direct local chat runs curation at its owned post-turn/exit lifecycle
   boundary because no daemon worker exists.
4. Manual CLI: `nuself memory update`.

Post-chat curation is a secondary effect after the assistant reply has already
been produced and persisted. Daemon curation failures belong to the worker
health and observability boundary and cannot alter the completed chat response.
Each requested or discovered observation ID is passed explicitly to
`MemoryCurator.run_once`. Memory does not accept a conversation store, state,
message, or identifier.

### Durable Observation And Recovery Plan

- `MemoryObservation` contains a stable `obs_...` ID, opaque source reference,
  ordered text fragments, observation time, optional trace correlation, and
  `pending`/`processed` status. `observe()` is idempotent and rejects an ID
  collision with different content.
- Before applying a ready model decision, persist one typed curator plan at
  `memory_curator_plans`. The plan owns the observation ID, opaque source
  reference, time, and structured actions. A plan write failure occurs before any
  candidate mutation and aborts the run.
- Candidate IDs produced from a curator plan are deterministic over the plan's
  source reference and action index. Resuming a plan reuses a repository
  candidate with that ID; an accepted candidate is not staged or accepted
  again, while a pending candidate may continue through the configured
  auto-accept policy.
- If candidate application is interrupted, the plan remains authoritative.
  The next run resumes it without invoking the model. After the observation is
  marked processed, its plan is removed.
- A plan is an authoritative typed record. Invalid JSON, observation identity,
  source reference, or actions are corrupt state: report `record_decode_failed` and abort rather than
  calling the model or guessing whether prior candidate effects committed. The
  typed `MemoryCuratorPlanCorruptError` crosses the curator boundary directly;
  callers do not erase it into a generic error with the same safe message.
- Curator runtime and operator tooling share one typed plan store and one
  `get()` read operation for path validation, strict decoding, corruption
  reporting, and exact-observation deletion. Recovery is a use of that read,
  not a parallel store API.
- `nuself memory plan show <observation>` exposes only operational metadata:
  observation ID, source reference, observation time, action count, action/type, optional
  target ID, and deterministic candidate ID. It must not print candidate
  title/body, tags, or model reason.
- `nuself memory plan discard <observation> --force` removes exactly that observation's
  plan and does not alter its observation or candidates. `--force` is mandatory
  because discarding an unfinished plan makes the observation eligible for a
  new model decision. Missing and corrupt plans remain explicitly
  diagnosable; there is no automatic discard.
- Curator plan/candidate/observation mutation is guarded by a stable advisory
  lock keyed by observation ID. Unrelated observations remain concurrent, and
  no conversation lock is shared or acquired.
- Lock acquisition is exclusive and non-blocking. A curator run that finds the
  same observation busy performs no model call or plan/candidate/observation mutation,
  emits
  `memory/curator_contended`, and returns a zero-change result. This is a normal
  deferred outcome, not a worker failure.
- `memory plan discard` holds the same lock across existence check and delete.
  Contention returns non-zero and leaves the plan untouched. `memory plan show`
  reads one atomic snapshot and does not acquire the mutation lock.
- Lock files are stable coordination inodes and are not deleted after release.
  Acquisition/release must close owned handles and preserve primary lock
  errors when cleanup also fails.
- A processed observation is an idempotent no-op.
- Deferred, candidate, and completion events are structured
  `memory` log events. The curator never appends raw text to `memory.log`;
  that file remains JSONL under the shared log contract.
- Memory curation owns one sealed audit registry and one
  `write_memory_audit()` operation shared by curator and optimizer. Unknown
  events and invalid status/error/metadata fail before the
  best-effort sink. Candidate audit metadata is identity-only: it may contain
  candidate ID, target ID, action, memory type, observation/source identity, and
  aggregate counts, but never candidate title/body or free-form model reason.
- Curator audit persistence is auxiliary. Failure to write one audit or its
  diagnostic cannot replace a saved candidate/entry, prevent an authoritative
  observation completion, or make a completed run eligible for replay.

### Quality Gate (`_has_memory_worthy_signal`)

- Inspect the producer-selected observation fragments.
- If concatenated text `< 120` chars AND contains none of the registered
  durable markers, return `processed_messages=0` without an LLM call. Marker
  matching uses the union of English, Simplified/Traditional Chinese, and
  Japanese durable-signal registries so mixed-language text is not excluded by
  the fast gate. The registries cover explicit remembering, future behavior,
  preferences, importance, decisions, goals/plans, reasons/questions, and
  always/never instructions. Language preference may guide the model response
  but must not restrict which registry is checked.

### Curator Agent Decision Contract

- Must return an actual typed `CuratorActionsOutput` through the shared
  framework-native `structured_response` boundary. Allowed actions are
  `create`, `update`, and `ignore`; curator does not prompt for JSON or parse
  response text.
- `create` and `update` actions must include `tags`: a non-empty list of short strings. Tags are part of the durable memory handle surface and must be copied to `MemoryCandidate` and any accepted `MemoryEntry`.
- The typed response uses a strict, extra-forbid curator schema with confidence
  constrained from zero through one, then every item is converted to
  `MemoryAction` before any item is dispatched. The curator must not keep a
  parallel text/dictionary parser or coerce unknown memory types to a fallback
  type.
- A shared typed `AgentError` from `agent.invoke(...)` defers the decision.
  Invocation and domain materialization are separate exception boundaries:
  `ValueError` raised while converting a successfully returned typed output
  also defers the complete decision, but a raw `RuntimeError` or `ValueError`
  raised by the agent implementation itself propagates as a contract bug.
  Domain code must not use `(RuntimeError, ValueError)` around both phases.
- Any invalid action defers the complete decision; valid siblings are not
  partially dispatched. Invalid actions include unknown/extra/coercive fields,
  confidence outside `[0, 1]`, `create`/`update` with blank `title`/`body`,
  empty normalized tags, unknown `type`, raw-transcript bodies (`>=2`
  occurrences of `user:`/`assistant:`), and `update` without a non-empty
  `entry_id`.
- LLM prompt includes: conversation summary, up to 12 existing memory entries, up to 12 profile items, and the current registered memory type names from `MemoryTypeRegistry`.

### Conflict Detection

- Before creating, check `MemoryTypeRegistry.conflicts(existing, incoming)` against up to 12 existing entries.
- If conflict → call `registry.merge(existing, incoming)` and produce `action="update"` candidate with `target_entry_id=existing.id`.
- If no conflict → produce `action="create"` candidate.

### Auto-Accept

- `MemoryCuratorSettings.auto_accept` defaults to `True`.
- When `auto_accept=True`, immediately call
  `accept(candidate.id, target_review_state="reviewed")` after saving.
  - For `create`/`update`/`merge`, the target is promoted to `reviewed` before
    the candidate is committed as accepted, inside the same transaction and
    compensation boundary.
  - An unknown memory type that is quarantined during the initial draft save
    remains `quarantined`; auto-accept does not bypass type recovery.
  - Validation or not-found failures retain the already-durable candidate as
    `pending`, emit `memory/auto_accept_failed` with its identity and compact
    exception chain, and allow the curator cursor to advance so the same source
    turn is not converted into another candidate.
  - Once the candidate is durable, auto-accept is a downstream convenience
    rather than the authoritative curation write. Any ordinary `Exception`
    retains the candidate's repository-visible final state, emits
    `memory/auto_accept_failed`, and allows the cursor to advance. This includes
    a typed compensation failure: its candidate/target state may require
    repair, but replaying the source through the model would create an
    additional candidate and is forbidden.
  - Process-control `BaseException` subclasses are not degraded.
- When `auto_accept=False`, candidates remain `pending`.
- A successful auto-accept memory-update trace records the candidate's actual
  `create` or `update` action. Trace recording is best effort through shared
  observability; trace and diagnostic-store failure cannot replace the saved
  reviewed entry.

## Optimization Flow (`MemoryOptimizer`)

### Trigger

- **Only manual CLI**: `nuself memory optimize --limit N`.
- No daemon background thread.

### Scope

- Load up to `memory_limit` (default `50`) most recently updated entries.
- Empty repository → return `reviewed=0`.

### Optimizer Agent Decision Contract

- Must return an actual typed `OptimizeActionsOutput` through the shared
  framework-native `structured_response` boundary. Allowed actions are
  `update`, `delete`, and `ignore`; optimizer does not prompt for JSON or parse
  response text.
- On failure → defer.
- The response and action models use strict types, forbid unknown fields, and
  constrain present confidence values from zero through one.
- Every action is validated and converted before any candidate is dispatched.
  One invalid action defers the complete decision; valid siblings are not
  partially dispatched.
- Every action requires a non-empty `entry_id`. Update actions additionally
  require non-blank `title`/`body`, reject raw-transcript bodies, and reject
  unknown memory type overrides.

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

Optimizer decision classification uses the same split boundary as curator:
typed `AgentError` from invocation and semantic `ValueError` from action
materialization defer; raw implementation exceptions preserve their identity.

### Optimizer Audit Projection

Optimizer deferred/completed/candidate-staged activity is written as structured
`memory` component events through the shared best-effort observability
boundary. It never appends raw text to `memory.log`. Candidate identifiers,
target identifiers, actions, and aggregate counts belong in typed metadata;
private candidate titles, bodies, and free-form reasons are not copied into
the audit record. An audit failure cannot replace a deferred result or an
already-persisted candidate.

The closed Memory curation taxonomy is:

| Event | Level | Status | Metadata |
|---|---|---|---|
| `curator_contended` | `info` | `deferred` | observation |
| `curator_deferred` | `info` | `deferred` | observation, source reference, zero processed count |
| `curator_completed` | `info` | `completed` | observation, source reference, processed/create/update/ignore counts |
| `candidate_merged` | `info` | `created` | candidate, target, memory type |
| `candidate_created` | `info` | `created` | candidate and memory type |
| `candidate_updated` | `info` | `created` | candidate, target, memory type |
| `optimizer_deferred` | `info` | none | zero reviewed count |
| `optimizer_completed` | `info` | none | reviewed/update/delete/ignore counts |
| `optimizer_candidate_staged` | `info` | none | action, candidate, target |
| `auto_accept_failed` | `warning` | `degraded` | required error plus candidate/action/type/nullable target |
| `trace_recording_failed` | `warning` | `degraded` | required error plus memory and one of `create`, `update`, `add`, `accept`, `merge`, or `import` |
| `curator_failed` | `error` | `error` | required error, no metadata |
| `post_chat_curation_failed` | `warning` | `degraded` | required error, no metadata |
| `chat_trace_recording_failed` | `warning` | `degraded` | required error, no metadata |

The sealed Memory audit registry owns these events even when a Chat client,
daemon request handler, or Memory CLI operation initiates the work. Those
callers use Memory-domain adapters and never construct raw `component=memory`
records. Post-chat completion is already represented by `curator_completed`;
clients must not emit a second `curator_changed` record or copy its free-form
summary into audit metadata. Chat trace failures use runtime context for
conversation correlation rather than duplicating the conversation id.

## Candidate Review Queue

### States

| State | Meaning | Final? |
|---|---|---|
| `pending` | Awaiting decision | No |
| `accepted` | Committed to durable memory | Yes |
| `rejected` | Discarded | Yes |

### Transitions

- **Accept `create`**: Converts to `MemoryEntry` (or `ProfileItem`). Manual
  review defaults MemoryEntry targets to `draft`; curator auto-accept requests
  `reviewed` as part of the same logical commit.
- **Accept `update`/`merge`**: Requires `target_entry_id`. Merges fields into target, preserving `id`/`created_at`, updating `updated_at`. Source refs and evidence concatenated; relations deduplicated.
- **Accept `delete`**: Requires `target_entry_id`. Deletes target from repository.
- **Reject**: Flips `review_state` to `rejected`.
- **Edit**: Updates any subset of `title`, `body`, `tags`, `importance`, temporal fields.

Accepting a candidate is one logical commit across the target collection and
the candidate review record. The repository enters the shared backend
transaction before creating, merging, or deleting the target and before
writing `review_state="accepted"`. SQLite provides atomic commit or rollback.
Any exception before commit leaves both the candidate and target at their
pre-operation state. Repositories do not perform file-era manual compensation
inside this transaction.

For MemoryEntry targets, `accept` accepts only `draft` or `reviewed` as the
requested final target state. The initial save still applies quarantine rules;
only a non-quarantined entry is promoted. Promotion happens before the
candidate final-state write, so a promotion failure rolls back the transaction
and leaves the candidate pending.
ProfileItem and delete targets have no MemoryEntry review-state transition.

### Entry Review States

| State | Meaning |
|---|---|
| `draft` | Newly created, not yet reviewed |
| `reviewed` | Accepted and durable |
| `quarantined` | Unknown type, awaiting recovery |
| `rejected` | Explicitly rejected |

## Memory Service (`MemoryService`)

The application composes one service for user-facing retrieval and bounded
entry mutation. It owns context packing, filtered counts, archive, and
importance updates; successful mutations are complete when the repository write
returns. Agent tools receive only this service and never the entry repository.
Repository bundles remain internal application resources for workflows that
coordinate candidates, sources, observations, curator plans, and profiles.
Memory intake, curation, and optimization receive typed structured agents from
CLI/application composition. Domain constructors do not resolve configuration
or model endpoints and retain direct agent injection for deterministic tests.

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

The chat memory skill may not conclude from its first empty tool result. It
must issue exactly one distinct broader `memory_search` using fewer, shorter,
or synonymous keywords before reporting that no matching stored memory was
found. The second empty result ends retrieval; the agent must not loop. This
conversation policy does not change deterministic `MemoryService`
scoring or make a claim that the authority contains no memories.

The one-shot `memory search` command uses the same ranked token query service
as the chat tool, then applies its CLI-only temporal and exact filters to those
matches. It must not retain the older whole-query substring behavior that can
disagree with chat for multi-keyword queries.

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
- Nodes and edges are computed from current SQLite memory entries when queried;
  there is no persisted graph or relation-index sidecar.
- Nodes are memory entries; edges generated from `entry.relations`.
- Edge IDs are deterministic: `{source_id}:{relation}:{target_id}`.

### Graph Operations

- `search_graph(query, node_type, limit, depth)`: text-match nodes, traverse adjacency up to `depth`, respect symmetry.
- `find_path(from_id, to_id)`: BFS shortest path with symmetry.
- `transitive_closure(node_id, relation)`: BFS along single relation name; respects symmetry.
