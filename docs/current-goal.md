# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Give Chat and its REPL/client surfaces closed, privacy-minimal audit contracts
without duplicating the existing runtime-event and service-tool registries.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory chat supervisor, client, LLM failover, tool-log, REPL transport,
   retry, input, completion, and cleanup audit producers.
2. Separate Chat-owned diagnostics from registered turn lifecycle events,
   shared service-tool logs, generic corrupt-record diagnostics, and
   cross-domain Memory/trace effects.
3. Define closed event families for Chat runtime, client, and interactive
   surfaces with exact privacy-minimal schemas.
4. Route direct producers through Chat-owned adapters without weakening
   best-effort or authoritative-effect semantics.
5. Remove copied previous errors, endpoint addresses, tool payloads, message
   content, and other redundant/private diagnostic metadata where the owning
   record already exists.
6. Preserve turn/request correlation through runtime context fields rather
   than duplicating identifiers into arbitrary metadata.
7. Run full quality gates, commit, and push.

## Out Of Scope

- No process-global registry containing every domain's audit events.
- No migration or rewriting of historical JSONL records.
- No redesign of registered `turn.started`, `turn.reused`, `turn.completed`,
  or `turn.failed` runtime envelopes and their existing audit projection.
- No replacement of the shared validated `service_tool_called` contract.
- No change to retry/failover decisions, thread persistence, final answers,
  or REPL liveness behavior.
- Memory curator and chat trace failures keep their owning component and will
  be reviewed with those domain contracts rather than relabeled as Chat.
- Generic corrupt-record diagnostics remain owned by observability.
- Generic audit-projection failure events remain owned by observability.

## Completion Evidence

- The inventory separates eighteen direct Chat/client/REPL diagnostics from
  registered `turn.*` runtime events, shared `service_tool_called` records,
  generic corrupt-record diagnostics, and Memory-owned trace/curator effects.
- One sealed `agent.chat.audit` registry owns all eighteen direct event
  identities and their exact level, status, error, and metadata contracts.
- Chat supervisor finalization/failover, LLM endpoint preference persistence,
  daemon/one-shot clients, tool-log failure reporting, and REPL history,
  completion, input, activity, retry, send, and cleanup boundaries now use
  Chat-owned adapters.
- LLM retry records retain endpoint index and model but no endpoint base URL.
- Transport retry records retain attempt bounds, failure phase, and
  possible-completion state; request correlation uses the standard
  `request_id` field and previous exception text is not duplicated.
- Activity degradation records retain decision-relevant booleans and stage,
  but no subscription id or duplicated request id. Send/tool-log failures no
  longer duplicate exception class names outside the structured error.
- Existing authoritative control flow is unchanged: audit failures cannot
  alter a reply, endpoint order, fallback, retry decision, REPL liveness, or
  cleanup aggregation.
- CLI Persona activity documentation was synchronized with the previously
  sealed content-free Persona audit contract.
- Direct tests cover all eighteen canonical schemas, unknown metadata,
  unknown identities, pre-sink rejection, and endpoint URL exclusion.
- Focused Chat/REPL suites: `195 passed`.
- Full test suite: `1958 passed`.
- Pyright 1.1.409: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

Pending this batch's implementation commit and push.

## Next Review Batch

Select after this batch is verified and published.
