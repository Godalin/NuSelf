# Shared Runtime Infrastructure Spec

## Purpose

NuSelf has several runtime boundaries: CLI commands, REPL commands, daemon
requests, agent tools, background workers, notifications, and structured logs.
They need shared infrastructure, but they do not all have the same delivery
semantics. The shared layer must make those semantics explicit instead of
building one untyped "message bus".

## Current Review Findings

The pre-infrastructure runtime has these recurring problems:

1. Daemon request dispatch is an `if request.type` chain while argparse and the
   REPL maintain separate registration conventions. Duplicate or missing
   handlers are detected only by tests or execution.
2. Daemon protocol payloads are generic dictionaries whose validation lives
   inside individual branches.
3. `write_log_event()` accepts free-form event/status strings and arbitrary
   metadata. There is no event identifier or schema version, and interactive
   deduplication hashes the complete serialized record.
4. The REPL repeatedly scans every log file to discover activity. Audit storage
   is therefore also acting as a slow cross-process activity feed.
5. Internal work uses unrelated transports: tuple queues, process-global
   callbacks, JSON dictionaries, log polling, and durable notification entries.
   Ownership, retry, and replay behavior differ but are not named in a common
   contract.
6. Some documentation still describes logs or the notification outbox as a
   generic event bus. Audit records and user notification delivery must not be
   treated as general command transports.

## Message Semantics

Every internal exchange belongs to exactly one of these categories:

| Category | Cardinality | Reply | Durability | Examples |
| --- | --- | --- | --- | --- |
| Request | one handler | required | transport-defined | daemon request, CLI command |
| Event | zero or more subscribers | none | optional projection | worker lifecycle, tool activity |
| Job | one worker at a time | completion state | required when retryable | reason export |
| Audit record | readers only | none | append-only | structured logs |
| Notification | adapter fan-out | delivery state | durable | outbox entry |

Code must not use an audit record as a command, a notification as a general
event, or an ephemeral event as the only record of retryable work.

## Handler Registry

`nuself.runtime.handlers.HandlerRegistry` is the shared in-process
request-dispatch primitive.

- A key maps to exactly one callable.
- Duplicate registration raises immediately.
- Registries are explicitly sealed after composition. Registration after
  sealing raises.
- Dispatch through an unregistered key raises `UnknownHandlerError`.
- A registry has no process-global singleton; the composition root owns it.
- Transport adapters remain responsible for decoding requests and encoding
  responses. Business handlers do not read sockets or argparse internals.
- Boundary-specific exception handling wraps registry dispatch rather than
  being duplicated in each handler.

The daemon request registry must be complete for every declared
`RequestType`. CLI and REPL registries should migrate only where the shared
primitive improves ownership; argparse remains responsible for argument
parsing and LangChain remains responsible for agent tool dispatch.

## Runtime Envelope And Correlation Context

The next infrastructure layer will introduce a versioned runtime envelope for
events and jobs. It must contain:

- stable message/event id;
- schema version;
- kind/name;
- producer component;
- creation timestamp;
- correlation fields (`request_id`, `turn_id`, `thread_id`, `job_id`,
  `trace_id`);
- JSON-safe typed payload.

Correlation context is inherited through one neutral runtime context. Logging
may project that context, but logging must not own it.

## Event Delivery

Ephemeral events use an in-process publisher/subscriber interface:

- publishing is synchronous by default so ordering and failures are explicit;
- subscribers are independently registered and cannot mutate the envelope;
- a logging subscriber may persist an audit projection;
- event delivery never performs hidden retries;
- cross-process live activity requires an explicit transport or cursor store,
  not repeated full-file scans presented as an event bus.

Events that can trigger durable or destructive state changes require a
request/job path with idempotency and explicit user approval. Replaying an
audit log must never repeat the action.

## Durable Jobs

Retryable background work uses typed job records, not tuples:

- stable job id and job kind;
- owner/resource ids;
- attempt count and timestamps;
- explicit pending/running/completed/failed state;
- serialized payload and last error;
- idempotent worker claim/completion transitions.

The reason-output export queue is the first migration target. Its existing
durable manifest remains authoritative while the in-memory queue becomes a
typed wake-up mechanism rather than the job record itself.

## Logging

Structured logs are an append-only sink and read model.

- `LogEvent` will become a projection of the shared runtime envelope.
- Every newly written event has a stable id and schema version.
- Component and event names come from registered definitions for core runtime
  events; domain extensions may register their own definitions.
- Metadata must be JSON-safe before it reaches the sink.
- File writes are serialized per project/component.
- Readers use stable event ids and incremental cursors; complete-record hashing
  is a legacy compatibility fallback only.
- Existing JSONL records without ids/schema versions remain readable.

The UI, transcript exporter, and diagnostics may read logs. They must not use
log replay to execute domain actions.

## Migration Order

1. Add and test the shared handler registry; migrate daemon request dispatch.
2. Centralize CLI handler binding/dispatch typing without replacing argparse.
3. Introduce runtime envelope and neutral correlation context.
4. Adapt structured logging into an envelope sink and add event ids, versions,
   serialized writes, and incremental cursors.
5. Introduce typed internal jobs and migrate reason export queue/callbacks.
6. Add an explicit event publisher for live in-process activity; retain
   cross-process compatibility until a dedicated transport is implemented.

Each migration must preserve external CLI/daemon protocol behavior unless its
governing spec and changelog explicitly describe a change.
