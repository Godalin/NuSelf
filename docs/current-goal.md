# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Give Persona consultation and discussion one closed, privacy-minimal audit
contract owned by the Persona subsystem.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory static graph, competitive discussion, chat consultation,
   Reflection integration, and lifecycle-trace audit producers.
2. Define one Persona-owned event taxonomy and privacy boundary.
3. Register exact level/status/error/metadata contracts for all owned events.
4. Route Persona graph/discussion failures through domain adapters.
5. Route chat and Reflection projections through Persona-owned adapters.
6. Verify prompts, candidate text, model reasons, synthesis, and discussion
   utterances never enter Persona audit records.
7. Run full quality gates, commit, and push.

## Out Of Scope

- No process-global registry containing every domain's audit events.
- No migration or rewriting of historical JSONL records.
- No change to activation, scoring, moderation, or Reflection decisions.
- No removal of discussion content from its authoritative result/trace
  structures; only the audit projection is minimized.
- Generic corrupt-record diagnostics remain owned by observability.
- Generic audit-projection failure events remain owned by observability.

## Completion Evidence

- The inventory covers static graph fallbacks, competitive discussion
  fallbacks/results, chat consultation/host/step projections, Reflection
  discussion projection, dynamic-persona lifecycle trace failures, and the
  interactive Persona command boundary.
- One sealed `persona.audit` registry owns all ten direct Persona event
  identities and their exact level, status, error, and metadata contracts.
- Persona graph, discussion, dynamic tools, CLI, Chat, Reflection, and REPL
  callers now use Persona-owned adapters instead of choosing raw log
  component/event/level/status combinations.
- Reflection no longer authors Persona records or copies candidate title/body,
  revised content, scores, discussion trace, or model reason into audit data.
- Chat audit records no longer copy user topics, persona synthesis,
  escalation/model reasons, winner/veto id lists, or discussion utterances.
  Content-free step records preserve progress visibility by ordinal.
- Failure records retain only their sanitized structured error plus a stable
  stage/action where required; persona ids and duplicate raw exception chains
  were removed from metadata.
- Unknown lifecycle actions still fail at the command implementation boundary;
  declared lifecycle trace failures are validated before entering the
  best-effort sink.
- Direct tests cover all ten canonical schemas, unknown metadata, unknown
  identities, pre-sink rejection, and privacy-minimal behavior.
- Focused Persona, Chat, Reflection, and REPL suites: `220 passed`.
- Full test suite: `1900 passed`.
- Pyright 1.1.409: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

Pending this batch's implementation commit and push.

## Next Review Batch

Select after this batch is verified and published.
