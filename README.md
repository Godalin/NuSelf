# NuSelf

[中文版 README](README.zh-CN.md)

NuSelf is a local AI mirror project. It is intended to grow into a personal agent with private memory, resumable conversations, lightweight thought-personas, proactive reflection, and controlled notifications.

The current implementation is an early CLI-first system:

- Local `nuself` command.
- Optional local background daemon over a Unix socket.
- A LangGraph-backed memory-aware chat agent that can run one-shot or through the daemon, with tool use for memory search, reflection inspection, memory curation, active reasoning threads, and trace provenance lookup.
- Storage-backed memory entries and profile items that can be listed, viewed, added, edited, deleted, and searched.
- Source ingestion for Markdown and plain text under ignored `private/sources/`, plus reviewable candidates extracted from imported chunks.
- Storage-backed trace records and long-run reasoning threads for durable thought provenance. Existing SQLite databases are selected automatically.
- Persisted chat threads with compressed conversation context.

LangGraph now backs the conversation runtime. The chat agent can invoke tools to search memory, list and dismiss pending reflection ideas, archive outdated memories, adjust importance scores, inspect active reasoning threads, and search thought traces. The internal persona system uses a shared competitive discussion flow for both chat and background reflection, with exact-schema agents generating activation decisions, distinct voices, and synthesis. Email and macOS notifications are supported when configured.

The canonical conversation runtime API is `ConversationGraphRuntime`; active
development does not retain the former `ChatAgent` class-name alias.
Configured models must return framework-native structured responses. The
no-model path is an explicit deterministic local response policy that returns
configuration guidance directly as typed chat output; it is not a fallback
model or a second prompted/fenced-JSON response protocol.

Approval-gated tools keep prompting and tool results authoritative when
secondary audit storage is unavailable; the failure is reported through
structured degraded diagnostics or a runtime warning.

Process-local log observers are isolated from business operations and from one
another. If both an observer and its structured failure record fail, NuSelf
emits a terminal runtime warning rather than silently losing the diagnostic.

Persona graph LLM failures retain deterministic contribution, synthesis, and
activation fallbacks while recording structured degradation; unavailable
diagnostics cannot interrupt endpoint failover.

Competitive persona discussions apply the same boundary to scoring,
participant selection, and moderator judgment, with diagnostics stored under
the calling project rather than implicit process state.

Atomic runtime-file writes preserve the original persistence failure even when
temporary-file cleanup also fails, exposing both errors and the residual path
to callers.
File-backed collection identifiers are opaque record keys: path syntax,
record/key mismatches, and symlink redirection are rejected at the shared
storage boundary.
`nuself dev migrate` now writes and validates a strict temporary SQLite
database, then atomically publishes it only after checkpoint, close, and fsync;
corrupt or ID-mismatched file records abort without exposing a partial
database.
Successful file-backed record deletion now includes parent-directory
synchronization; a visible deletion whose crash durability is unknown is
reported distinctly instead of being treated as an ordinary failed unlink.
Memory candidate acceptance applies the same distinction across its target and
review records: a visibly accepted, matching pair is preserved and reported as
an ambiguous commit when crash durability cannot be proven; failed read-back
or an unexpected target remains ambiguous and retains its secondary evidence
instead of triggering destructive compensation, while a candidate proven
pending still triggers target compensation.
File-backed transaction batches now use a stable cross-process advisory lock,
and notification outbox admission performs idempotency lookup plus insertion
inside that backend transaction.
Notification delivery also persists one state per stable adapter (`log`,
`email`, or `macos`). If a later adapter crashes, recovery skips channels whose
terminal success or failure was already recorded instead of implicitly
retrying them. CLI/REPL send and dismiss operations preserve that adapter plan
and history.
Reason export manifest-write and retry-callback failures schedule bounded,
delayed online reconciliation, so a durable non-terminal job can recover
without a daemon restart or an immediate retry loop.
Persisted chat threads are decoded fail-closed: every message must be a valid
object, indexes reject booleans, and the absolute next index must exactly match
the retained message window.
The memory curator's short-text fast gate recognizes durable signals across
English, Simplified/Traditional Chinese, Japanese, and mixed-language turns.
Shared model endpoint failover classifies structured timeout, rate-limit, and
transient server statuses through exception/response chains; it never matches
rendered provider error text.
Email notification HTML escapes body and link attributes independently, accepts
only canonical supported `nuself://` deep links, and rejects header injection
before opening SMTP.
Shared runtime timeout validation now gives job admission, delayed scheduling,
and owned calls identical bool/NaN/infinity/negative-value behavior.
Thought-pack export names are portable across supported host filesystems,
including rejection of Windows device names and trailing dots.

Daemon instance-lock acquire and release likewise preserve simultaneous lock
operation and handle-close failures, so ownership errors are not hidden by
cleanup.

SQLite transaction cleanup errors expose both the failed primary operation and
failed rollback while resetting thread-local transaction state.

Reason execution failure logs are secondary to the original advancer,
scheduler, or output-runner outcome, including when structured audit storage
is unavailable.
Reason advances accept only the framework-returned typed `ReasonStepOutput`;
malformed kinds, terminal decisions, confidence values, evidence references,
and tracked items fail validation instead of being filtered or defaulted.
Persona activation, contribution, and synthesis likewise require their exact
strict structured-output model; dictionary results and coercive or out-of-range
fields participate in endpoint failover instead of entering persona state.

Reflection auxiliary diagnostics cannot interrupt a persisted cycle or turn a
corrupt schedule's fail-closed block/cooldown decision into an exception.

LLM endpoint preference and chat response diagnostics are auxiliary to accepted
model output, so their storage failure cannot discard a response or interrupt
configured retry, failover, and local fallback.

Daemon reason-export audit records are auxiliary to durable manifest,
composition, retry, reconciliation, and shutdown decisions; audit failure
cannot alter those worker outcomes.

ReasonService lifecycle audits and provenance traces are auxiliary to committed
thread, step, status, and deletion state, preventing projection failures from
turning successful operations into apparent failures.

Memory curator activity now remains structured in `memory.log`; curator trace
and audit failures, plus organizer completion audit failures, cannot replace
already-persisted memory or reflection results.
Curator action batches are validated completely before candidate dispatch.
Unknown or coercive fields, out-of-range confidence, and incomplete mutations
defer the source range instead of partially applying valid sibling actions.
An explicit memory or profile importance of `0.0` remains zero across file and
SQLite round-trips; defaults apply only when the wire field is absent.

Email and macOS delivery-failure diagnostics cannot replace a definitive
adapter failure or prevent the outbox from persisting the failed attempt.

Daemon request audits cannot replace the original chat error, invalidate a
completed response, or prevent an accepted shutdown request.

Daemon lifecycle audits from the server, CLI, and interactive restart share
one observable projection boundary and cannot alter lifecycle results.

Daemon response encoding completes before socket delivery. Invalid or
oversized handler responses are observed separately and fall back to a bounded
error frame with the same request identity when delivery is still possible.

Daemon client errors retain their transport phase and request identity. REPL
retry decisions are structural: transient transport/frame failures may retry
the same stable turn, while local request encoding and typed payload schema
failures do not.

REPL daemon-activity transport is auxiliary: open, poll, final-drain, and close
failures are observed with structured client context, cannot alter chat
results, and recover persisted turn events through the scoped cursor when
possible.

The live-chat send thread observes unexpected ordinary callback failures as
non-retryable turn failures, while process-control exceptions cross back to the
main thread unchanged after subscription cleanup.
Caught callback, projection, protocol-decode, and rollback diagnostics are
sanitized before entering terminal or wrapper messages while retaining their
original exception objects for control flow and provenance.

REPL exit runs transcript auto-save and memory curation exactly once each.
Both cleanup steps are attempted, and named cleanup failures retain any
existing main-loop exception as their explicit cause.

Daemon and REPL lifecycle cleanup use one shared ordered runner that retains
named `BaseException` failures; each domain still owns ordering, diagnostics,
and primary-error propagation.

## Project TODOs

Project progress is tracked in [`docs/TODOs.md`](docs/TODOs.md). Short-term implementation focus lives in [`docs/current-goal.md`](docs/current-goal.md).

## Branch And Version Policy

- `main` is the stable, releasable branch.
- `dev/v0.3.x` is the active optimization branch.
- `feature/*` branches are isolated experimental work.
- `patch` versions cover stabilization, refactors, and fixes.
- `minor` versions add new subsystems or cognitive capabilities.
- `major` versions mark architecture maturity milestones.

## Requirements

- Python 3.12 or newer on Linux or macOS. Windows is not currently supported.
- `uv`.

The active development package is `0.3.0rc1`.

## Install And Run

From the project root:

```bash
uv run nuself --help
```

Run tests:

```bash
uv run --locked pytest
uv run --locked pyright
```

## Configuration

NuSelf configuration is unified in a single YAML file:

```text
private/config.yaml
```

Configuration priority (highest to lowest):
1. `private/config.yaml`
2. Hardcoded defaults in code

### LLM Configuration

```text
llm:
  - base_url: https://api.openai.com/v1
    api_key: ""        # Leave empty for local fallback
    model: gpt-4.1-mini
    timeout_seconds: 60
  # Optional Anthropic endpoint:
  # - anthropic: true
  #   api_key: ""
  #   model: claude-sonnet-4-5
```

Provider protocol is explicit. OpenCode Go's MiniMax M2.7 route is
OpenAI-compatible:

```yaml
llm:
  - base_url: https://opencode.ai/zen/go/v1
    api_key: ""
    model: minimax-m2.7
```

Use the protocol documented by the gateway for the selected model; NuSelf does
not infer it from the URL or model name. `nuself dev config` prints the
effective provider selection while redacting every API key.

### Chat Settings

```text
chat:
  request_timeout_seconds: 120
  context:
    recent_messages: 12
    summary_trigger_messages: 18
    summary_target_chars: 2400
```

### Daemon Intervals

```text
daemon:
  memory_curator:
    interval_seconds: 300
  reflection_scheduler:
    check_interval_seconds: 60
  notification_delivery:
    interval_seconds: 30
```

### Reflection System

```text
reflection:
  scheduler:
    interval_seconds: 3600
    cooldown_seconds: 300
    quiet_start_hour: 22
    quiet_end_hour: 7
    daily_cap: 5
    jitter_percent: 20
    max_pending_entries: 20
  gate:
    relevance_threshold: 0.5
    persona_discussion_threshold: 0.7
  moderator:
    max_discussion_rounds: 10
    moderator_convergence_patience: 5
```

See `examples/private/config.yaml` for a complete annotated example and additional sections (email, macOS notifications, experimental features).

Inspect effective configuration:

```bash
uv run nuself dev config
```

## Private Directory

Real personal data lives in the ignored root directory:

```text
private/
```

This directory is not committed to Git. It contains local profile notes, memory entries, chat threads, runtime files, daemon logs, derived indexes, and future private configuration.

The repository includes a safe public sample directory:

```text
examples/private/
```

Use the sample directory for documentation, tests, and demos. Do not put real personal memory there.

## Chat

One-shot chat works without a daemon:

```bash
uv run nuself chat
uv run nuself chat --message "hello"
```

The shortest daemon-backed entrypoint is the root command. It connects to the current daemon, or creates one and then connects:

```bash
uv run nuself
uv run nuself --message "hello"
```

If a daemon is running, `chat` sends the message to the daemon:

```bash
uv run nuself daemon start
uv run nuself chat --message "hello from daemon"
uv run nuself daemon stop
```

Require an existing daemon:

```bash
uv run nuself chat --require-daemon --message "hello"
```

Attach to an existing daemon conversation:

```bash
uv run nuself attach
uv run nuself attach --message "continue"
uv run nuself daemon attach
uv run nuself daemon attach --message "continue"
```

Without `--message`, `chat` and `attach` enter interactive mode. When terminal support is available, line editing and arrow-key history are backed by `private/runtime/interactive_history`. Dynamic completion and history persistence are best effort: storage failures are recorded as degraded events but do not prevent typing or accepting a line. The session header is shown at startup, after every completed chat turn, and after commands that request a thread or status redraw. Input starting with `:` is treated as an interactive command. Use `:dev status` for daemon/thread status, `:dev logs` for recent activity events, and `:mem` to preview current memory entries. Read-only memory inspection shortcuts include `:mem search <query>`, `:mem show <entry-id>`, `:mem review`, `:mem review <candidate-id>`, `:mem profile <query>`, `:mem sources`, and `:mem source <source-id>`. Use `:reason` for long-run reasoning threads, `:trace` for thought provenance records, and `:inbox` for reflection/notification items. Type `:q`, `:quit`, `:exit`, or send EOF to leave; unknown commands print interactive help and keep the session open.

If styled terminal input is unavailable because of a declared terminal or IO
failure, NuSelf records `chat/interactive_prompt_failed` and falls back to
built-in input. EOF, keyboard interrupt, and unexpected prompt failures retain
their normal control-flow behavior.

Non-LangChain local models may return plain text or a valid JSON/fenced-JSON
response envelope. Protocol-looking output is decoded strictly; malformed
protocol JSON and invalid response fields are never displayed as raw answers.

Current chat uses a LangGraph-backed conversation runtime that searches memory entries, derived profile items, and imported source chunks, appends turns to `private/threads/default.json`, and compresses older context into a thread summary once the conversation grows. The agent can also invoke tools during conversation: `search_memory` for targeted retrieval, `list_pending_reflections` / `dismiss_reflection` to inspect and manage proactive ideas, `archive_memory` / `update_memory_importance` to curate durable memory, `list_active_reasoning_threads` / `show_reasoning_thread` to inspect durable reasoning state, and `search_trace` / `show_trace` to inspect thought provenance. The memory search is deterministic lexical retrieval with descriptor-aware type hints, type/tag filters, relation expansion over existing memory links, and ranked match reasons; vector and graph indexes are planned as derived retrieval layers.

Chat lifecycle activity is published as registered `turn.started`,
`turn.completed`, `turn.failed`, and `turn.reused` events. A completed event is
emitted only after the thread update is durably saved. Structured audit and
daemon live-activity projections retain the same event identity and
correlation, while a failed subscriber cannot replace the reply or mask the
original chat failure.

Daemon-backed, one-shot, and interactive retry client operations use one
`source="client"` runtime scope. Their transport, retry, completion, and
post-turn curation logs therefore share thread/turn correlation, preserve any
caller request/job/trace identity, and restore the caller context afterward.

Thread-scoped dynamic persona prompt files are authoritative; their derived name index is validated and atomically rebuilt when missing, malformed, or stale, so damaged lookup metadata does not hide healthy personas or retain old names after a rename.

Global and thread-scoped `persona_think` calls use the shared framework-native
free-text agent capability. Natural-language conclusions remain plain text,
while empty results and unavailable endpoints produce explicit tool errors
instead of a hidden local response; free-text and structured agents share the
same endpoint failover infrastructure.

Reflection relevance and candidate generation use the shared LangChain structured-agent boundary with strict typed response schemas. Missing fields, extra fields, out-of-range scores, malformed batches, string booleans, and unknown candidate types take the existing safe fallback instead of being defaulted, clamped, coerced, or partially accepted.

Persona activation and competitive discussion use the same strict typed-output
rule. Malformed activation, scoring, participant-selection, or moderator JSON
takes the existing safe fallback instead of coercing string booleans or numeric
strings, or partially accepting a malformed selection.

Reflection cooldown and daily-cap state is versioned and written atomically.
Malformed or partial state blocks reflection scheduling with a structured
diagnostic instead of being mistaken for a first run and disabling rate
limits.

The last successful LLM endpoint is stored as a versioned, atomically written
derived preference. Invalid or stale endpoint state is diagnosed and safely
falls back to configured endpoint order, so damaged preference metadata cannot
disable model access.

Each project root permits one daemon owner through a cross-process instance
lock. Concurrent daemon starts cannot unlink a live daemon's Unix socket or PID
files; the contender exits with a diagnostic while the owner continues
serving.

Daemon PID metadata is atomically published. Missing PID state remains a
normal stopped condition, while malformed or non-positive PID content is
diagnosed instead of silently being presented as ordinary absence.

Runtime state and generated reason artifacts use one shared atomic writer with
unique temporary files and cleanup on failure. Thread, persona, and reason
subsystems no longer maintain divergent replacement implementations.

Recoverable CLI persona lifecycle trace failures are recorded as
`persona/trace_recording_failed` without reversing the already-successful
create, enable, or disable mutation.

Missing `private/email.toml` still means email delivery is intentionally
disabled. If the file exists but is unreadable or invalid, NuSelf records a
payload-safe `outbox/email_config_invalid` diagnostic rather than silently
treating it as absent.

`private/threads/default.json` is shared working memory for the current NuSelf mind. Multiple terminal attachments to the same daemon share it. The thread store serializes writes with a lock so concurrent turns do not overwrite each other.
Rename, branch, archive, restore, and delete use the same stable per-thread
lock identities, so lifecycle commands cannot race an in-flight chat write or
split one logical lock across recreated files.

The memory curator runs in the background in the daemon and also runs when interactive chat exits. It uses LangChain's native structured-agent boundary to decide whether new working-memory turns should create, update, or ignore long-term memory. Trivial chat is ignored, similar existing memories should be updated instead of duplicated, and raw chat transcripts are rejected. By default, accepted candidates are automatically promoted to durable memory entries (`auto_accept=True`); validation failures leave the recoverable candidate pending and emit a diagnostic instead of disappearing silently. Per-thread curator cursors are written atomically; a malformed cursor stops that curation run with a corruption diagnostic instead of replaying old conversation history. A separate memory optimizer can be run manually, less frequently, to consolidate messy existing entries through the same typed boundary. Its generated actions use strict schemas and are validated as one batch before candidate dispatch, so one invalid action defers the complete decision without partial candidates. Update events are written to `private/logs/memory.log`, and interactive chat prints compact activity lines for new chat, daemon, and memory events.

When synchronous post-chat curation has a recoverable failure, the completed
assistant reply is still returned and the failure is recorded as
`memory/post_chat_curation_failed` with the turn correlation context; it is not
silently presented as an ordinary no-op.

The current conversation graph is intentionally small: it preserves the CLI and daemon protocol boundary while keeping room for later persona subgraphs and richer agent routing.
Its compression node uses the shared free-text agent capability when a
LangChain model is available. If that capability is absent, fails, or returns
empty text, the node retains a bounded deterministic transcript-tail summary
so context persistence still completes without inventing content.
Chat endpoint retry is also tool-safe: once an agent invocation has produced
any tool outcome, a later model failure cannot start a fresh agent run or
switch endpoints and replay that tool. Failures before the first tool retain
the bounded retry and failover policy.
Agent middleware carries each tool outcome as an immutable typed record with
separate result and error states. Reason tool activity is therefore still
logged accurately when the enclosing reasoning agent fails after a tool ran;
the original agent failure remains authoritative.
Reason advancement now uses every configured endpoint for availability
failover, but only before its first tool outcome. A provider failure after a
workspace, persona, or service tool ran becomes a chained reason error instead
of starting another agent that could repeat the operation.

## Daemon

Start, inspect, and stop the local daemon:

```bash
uv run nuself daemon start
uv run nuself daemon status
uv run nuself daemon health
uv run nuself daemon list
uv run nuself daemon logs
uv run nuself daemon attach --message "continue"
uv run nuself daemon stop
uv run nuself daemon restart
```

Structured local logs can also be inspected with:

```bash
uv run nuself dev logs
uv run nuself dev logs --component chat --tail 20
uv run nuself dev logs --component memory --json
uv run nuself dev logs --component reflection --tail 10
uv run nuself dev logs --component storage --tail 10
```

Failures in secondary audit or thought-trace recording appear as structured
`*_failed` warnings without changing the result of the primary operation.
Shared backend lifecycle failures are written under the `storage` component.
Malformed stored records are isolated during collection reads and reported as
payload-safe `record_decode_failed` warnings. Reason-thread scheduling
timestamps must include a timezone, so corrupt cooldown state cannot silently
make a thread eligible for background advancement.

The SQLite backend applies the same isolation to malformed dynamic-column JSON:
healthy neighboring rows remain readable, direct lookups stay strict, and
diagnostics never include the corrupt column contents. Explicit backend
shutdown checkpoints the WAL and surfaces checkpoint or connection-close
failures; a failed close remains retryable rather than being marked complete.
Invalid reason-export manifests stop composition safely. Job listing reports
and isolates malformed manifests without exposing their contents, while direct
lookup and filesystem failures remain visible; invalid progress and retry-state
persistence failures are reported in daemon logs. Missing progress is normal,
but unreadable or malformed progress is diagnosed and never partially coerced.
Generated reason-export chapter plans also use an exact structured-agent
schema. Their ranges must form one ordered, contiguous partition of all source
steps; malformed or partial plans fall back as a whole to deterministic
section planning rather than repairing generated fields or accepting siblings.
Export body composition uses the shared free-text agent capability. Missing
endpoints, invocation errors, or empty text fail the composition attempt and
enter the durable retry state machine instead of producing a successful
artifact containing a local configuration warning.

Check system health:

```bash
uv run nuself dev health
```

Daemon health reflects both scheduled-iteration failures and unexpected worker
target exits. Worker lifecycle activity is published as registered
`worker.started`, `worker.failed`, and `worker.stopped` events, then projected
to structured audit logs with the same identity and `daemon.worker.<name>`
source. A failed audit or other event subscriber falls back to a runtime
warning without changing worker execution, health transitions, or the
scheduled loop. Shutdown attempts every owned cleanup step and retains
simultaneous failures; `daemon/stopped` is emitted only after workers,
project-scoped storage, socket, and PID cleanup all succeed. SIGINT/SIGTERM
handlers are temporary daemon ownership and the host process's exact previous
handlers are restored on exit.

Quick status overview:

```bash
uv run nuself dev status
```

Without a subcommand, `daemon` shows daemon subcommand help.

Daemon runtime files are stored under:

```text
private/runtime/
private/logs/
```

The first protocol is one request and one response as newline-complete UTF-8
JSON over a Unix domain socket at `private/runtime/nuself.sock`. Frames are
bounded to 1 MiB; stalled, incomplete, extra, malformed, and mismatched
responses fail as transport errors instead of retaining a server thread or
being accepted as partial JSON. Envelope fields are exact and validated in
both directions: duplicate or unknown fields, empty request ids, non-finite
payload numbers, and inconsistent response error states are rejected.
Each request type also validates its exact payload fields; invalid optional
values are not silently replaced by defaults, with `echo` retained as the
explicit arbitrary-object exception.
Typed client operations validate complete success payloads for chat, health,
activity, ping, and shutdown. A daemon rejection stays distinct from a
malformed successful response, and malformed nested worker or activity records
are never silently skipped.
Queued reason exports carry their immutable runtime context into worker
execution and retries, so logs retain top-level request, turn, trace, job, and
thread correlation while identifying the consuming worker as their source.
Durable notification intents likewise store their originating runtime context
directly on the outbox record. Each adapter chain restores that context under
the notification worker source, while older context-free records remain
readable.
Every scheduled memory, reflection, reason, and notification-delivery tick
also receives a fresh job identity. Nested work and failure diagnostics share
that identity, and reused worker threads begin each iteration with an isolated
context.
Short-lived deferred callbacks can explicitly bind the immutable runtime
context of the logical operation they continue. Interactive chat uses this
boundary for its send thread, while transcript capture remains limited to the
chat path and does not absorb concurrent background subsystem audit records.
Reason advances also scope workspace and thread-local persona tools through
this shared context, preserving request/job correlation while selecting the
active durable reason thread.
Reason commands distinguish declared not-found, prompt, advance, and
transition outcomes from unexpected implementation failures, so only known
domain errors are converted into concise CLI or REPL messages.
Topic-specific reason prompts are generated as exact `ReasonPromptOutput`
models through the shared structured-agent boundary. Missing models,
invocation failures, or malformed prompt output stop thread creation before
any partial thread is persisted.
Process-local live log observers remain separate from correlation identity:
nested observers compose in order, projection failures are isolated after the
audit write, and observers are not implicitly carried into new worker threads.
Runtime envelopes and log events share one strict JSON freeze/thaw boundary,
so persisted audit data and live activity receive the same immutable metadata
snapshot without retaining aliases to caller-owned containers.
Per-turn agent tool deduplication uses the same strict JSON semantics for
canonical cache identities. Non-JSON arguments bypass caching rather than
colliding through string coercion or preventing LangChain from handling them.
Authoritative file, SQLite collection, and workspace persistence validates
strict JSON before mutation. Non-finite values cannot leave partial files,
dynamic columns, replaced rows, or partially committed workspace batches.

## Notifications

The notification outbox is a durable user-attention queue for "something
happened, go look at X" alerts. It is separate from the internal runtime event
bus and may be used by background jobs that need to notify the user (reflection
with `auto_notify`, memory curator, etc.). Persisted notification timestamps are
timezone-aware; malformed records are reported and isolated rather than
silently influencing retention cleanup.

```bash
uv run nuself inbox notify list
uv run nuself inbox notify show <entry-id>
uv run nuself inbox notify show -i <index>
uv run nuself inbox notify send <entry-id>
uv run nuself inbox notify dismiss <entry-id>
uv run nuself inbox notify dismiss -i <index>
uv run nuself inbox notify clear
uv run nuself inbox notify watch          # poll for new entries
```

Notifications include a deep link. Open one directly:

```bash
uv run nuself thread open --deep-link "nuself://thread/reflections"
```

The macOS adapter delivers pending entries as system notifications via `osascript`. The email adapter reads SMTP credentials from `private/email.toml` and sends via SMTP. Both support dry-run mode for testing.

## Reflection

The daemon runs a proactive reflection scheduler that generates ideas from recent threads, memory entries, and source documents. Ideas are scored for novelty, confidence, urgency, and interruption cost, then debated by a randomized set of internal personas. Discussion scoring, participant selection, and moderator judgment use exact-schema agents through the shared LangChain structured-output boundary; malformed decisions use bounded stage-specific fallbacks rather than text reparsing or value repair. Approved ideas are stored in `private/reflections/` as first-class entries with `pending`, `dismissed`, or `archived` status.

Reflection ideas can be inspected and managed with:

```bash
uv run nuself inbox reflection list
uv run nuself inbox reflection list --status pending
uv run nuself inbox reflection list --status dismissed
uv run nuself inbox reflection show <id>
uv run nuself inbox reflection show -i <index>
uv run nuself inbox reflection dismiss <id>
uv run nuself inbox reflection archive <id>
uv run nuself inbox reflection promote <id>
```

When `reflection.auto_notify` is enabled in config, a brief notification is also created in the outbox pointing to the new reflection idea.

## Reason And Trace

Reason stores explicit long-run questions as durable threads. Trace stores provenance records for important chat turns, reason thread creation, reason advances, and reflection promotion.

```bash
uv run nuself reason list
uv run nuself reason start "What should I keep thinking about?"
uv run nuself reason show <id-or-index> --by-index
uv run nuself reason advance <id-or-index> --by-index
uv run nuself reason pause <id-or-index> --by-index
uv run nuself reason resume <id-or-index> --by-index
uv run nuself reason resolve <id-or-index> --by-index
uv run nuself reason archive <id-or-index> --by-index
```

```bash
uv run nuself trace list
uv run nuself trace show <id-or-index> --by-index
uv run nuself trace search "reason thread"
```

Promote a pending reflection into a reason thread:

```bash
uv run nuself inbox reflection promote <id-or-index> --by-index
```

## Threads

List, inspect, and manage conversation threads:

```bash
uv run nuself thread list
uv run nuself thread show <thread-id>
uv run nuself thread new <thread-id>
uv run nuself thread rename <old-id> <new-id>
uv run nuself thread branch <source-id> <new-id> [--index <n>]
uv run nuself thread archive <thread-id>
uv run nuself thread unarchive <thread-id>
uv run nuself thread archived
uv run nuself thread delete <thread-id>
```

Open a thread in interactive mode:

```bash
uv run nuself thread open <thread-id>
uv run nuself thread open <thread-id> --message "hello"
```

In the REPL, switch threads with `:thread <id>`, view recent messages with `:history`, inspect sources with `:mem sources`, search memory with `:mem search <query>`, archive the current thread with `:archive`, restore an archived thread with `:unarchive <id>`, list archived threads with `:archived`, and delete the current thread with `:delete`. If persisted thread history is malformed or unreadable, `:history` reports the load error instead of presenting the thread as empty. Recoverable `:history` and `:persona` failures also write privacy-bounded structured diagnostics; logging degradation cannot replace the command error or close the session.

## Memory Entries

Chat is the primary source of new memory. After chat turns, NuSelf runs the Memory Curator Agent and prints a `[memory] ...` summary when durable memory changes are created or updated.
Curator decisions are based on discussion depth, quality, and durable signal rather than a fixed number of chat turns.

Manual memory commands remain available as maintenance tools. Memory is stored as clear entries under:

```text
private/memory/entries/
```

Add an entry:

```bash
uv run nuself memory add \
  --body "Prefer explicit assumptions and source-aware reasoning." \
  --tag style
```

`memory add` infers the memory type and title through LangChain's native structured-output boundary. Its generated metadata must provide a complete strict schema, including 1–4 tags and confidence/importance scores from zero through one; missing typed output or invalid model output fails the command instead of being reparsed or repaired. Use `--type` or `--title` only when you need an explicit maintenance override.

List entries:

```bash
uv run nuself memory list
```

Preview recent memory entries:

```bash
uv run nuself memory preview
uv run nuself memory preview --limit 20
```

Show one entry:

```bash
uv run nuself memory show <entry-id>
```

Edit an entry:

```bash
uv run nuself memory edit <entry-id> \
  --title "Clarity matters most" \
  --body "Prefer explicit assumptions, concrete evidence, and source-aware reasoning."
```

Search entries:

```bash
uv run nuself memory search "clarity"
```

Export all memory entries to JSON:

```bash
uv run nuself memory export -o backup/memory.json
uv run nuself memory import backup/memory.json
```

Run the memory curator immediately:

```bash
uv run nuself memory update
```

Consolidate existing memory entries:

```bash
uv run nuself memory optimize
uv run nuself memory optimize --limit 100
```

Delete an entry:

```bash
uv run nuself memory delete <entry-id>
```

List registered memory types:

```bash
uv run nuself memory types
```

Rebuild the derived memory index:

```bash
uv run nuself memory reindex
```

Inspect derived memory relations:

```bash
uv run nuself memory relations
uv run nuself memory relations --relation supersedes
uv run nuself memory relations --source-id <entry-id>
uv run nuself memory relations --target-id <entry-id>
```

Inspect the derived symbolic graph:

```bash
uv run nuself memory graph nodes
uv run nuself memory graph nodes --type belief
uv run nuself memory graph edges
uv run nuself memory graph edges --relation related_to
uv run nuself memory graph edges --source-id <entry-id>
uv run nuself memory graph edges --target-id <entry-id>
uv run nuself memory graph search "graph retrieval"
uv run nuself memory graph search "graph retrieval" --type concept --limit 5
```

The derived memory, relation, and symbolic graph artifacts are written to:

```text
private/derived/memory_index.json
private/derived/relation_index.json
private/derived/symbolic_graph.json
```

## Source Documents

Import Markdown or plain-text source material into ignored local storage:

```bash
uv run nuself memory source ingest private/sources/my-note.md --tag notes
uv run nuself memory source ingest private/sources/ --tag archive
```

Imported document metadata is stored under `private/sources/documents/`, and stable chunks are stored under `private/sources/chunks/`.

Inspect imported sources:

```bash
uv run nuself memory source list
uv run nuself memory source show <source-id>
uv run nuself memory source chunks <source-id>
uv run nuself memory source search "durable citation"
```

Extract reviewable profile candidates from an imported source:

```bash
uv run nuself memory source extract <source-id>
```

The extraction step creates `profile_fact` candidates in the review queue with structured source evidence. Accepted profile candidates are stored under `private/profile/items/`, and you can inspect them with:

```bash
uv run nuself memory profile list
uv run nuself memory profile search "concise"
uv run nuself memory profile show <profile-id>
```

Profile search supports deterministic filters for `--type`, `--tag`, `--observed-from`, `--observed-to`, and `--valid-on`.

Supported front matter fields are `title`, `date`, `tags`, `origin`, and `privacy`. Source chunk references use the form `source:<source-id>:<chunk-index>`.

`memory reindex` rebuilds `private/derived/memory_index.json`, `private/derived/relation_index.json`, `private/derived/source_index.json`, and `private/derived/profile_index.json` from authoritative memory, source, and profile records.

Delete an imported source and its derived review artifacts:

```bash
uv run nuself memory source delete <source-id>
```

Delete a derived profile item directly:

```bash
uv run nuself memory profile delete <profile-id>
```

## Memory Entry Types

Supported entry types:

- `source_note`
- `profile_fact`
- `belief`
- `preference`
- `goal`
- `concept`
- `style_trait`
- `episode`
- `open_question`
- `instruction`

## Project Docs

- [Current architecture](docs/architecture.md)
- [System specifications](docs/spec/) — behavioral contracts for CLI, memory, reflection, notifications, etc.
- [Active development goal](docs/current-goal.md)
- [Unresolved backlog](docs/TODOs.md)
- [Changelog](CHANGELOG.md)
- [Agent instructions](AGENTS.md)

## Development Policy

NuSelf is in active early development. Interfaces are expected to move quickly. Do not preserve obsolete CLI commands, protocol fields, schemas, or Python APIs unless current docs explicitly require compatibility.

When functionality, commands, configuration, runtime behavior, or other user-visible behavior changes, update both [README.md](README.md) and [README.zh-CN.md](README.zh-CN.md) in the same change.
