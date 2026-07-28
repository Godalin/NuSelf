# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Give Memory curation one closed, privacy-minimal audit contract.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory curator, optimizer, and secondary-effect failure audit producers.
2. Define the complete Memory curation taxonomy and metadata minimization.
3. Register exact level/status/error/metadata contracts for all owned events.
4. Route curator and optimizer projections through domain adapters.
5. Route auto-accept and trace failures through a validated secondary wrapper.
6. Verify private titles/reasons never enter new curation audit metadata.
7. Run full quality gates, commit, and push.

## Out Of Scope

- No process-global registry containing every domain's audit events.
- No migration or rewriting of historical JSONL records.
- No change to curator/optimizer decisions, candidate persistence, or cursor state.
- Generic corrupt-record diagnostics remain owned by observability.
- Generic audit-projection failure events remain owned by observability.

## Completion Evidence

- The inventory identified nine primary curator/optimizer projections plus
  registered `auto_accept_failed` and `trace_recording_failed` secondary-effect
  failures.
- One sealed `memory.audit` registry now owns all eleven event identities and
  their exact level, status, error, and metadata contracts.
- Curator and optimizer no longer accept arbitrary event/level/status strings;
  their adapters resolve definitions before the best-effort log sink.
- `run_memory_curation_observed(...)` validates secondary-effect failure
  identity and metadata before executing auto-accept or trace recording.
- Shared `run_observed_best_effort(...)` now accepts declared failure level and
  status rather than forcing every domain diagnostic to warning/degraded.
- Candidate curation records retain IDs, target IDs, action, and memory type
  but no longer copy private candidate titles or free-form model reasons.
- Corrupt cursor diagnostics remain under the generic record-decoding contract
  and are not duplicated into the curation registry.
- Direct tests cover all eleven canonical schemas, unknown fields, unknown
  identities, pre-sink rejection, private metadata minimization, and declared
  secondary-failure presentation.
- Focused Memory audit, curator, optimizer, and observability suites:
  `92 passed`.
- Full test suite: `1877 passed`.
- Pyright 1.1.409: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is ready to publish through implementation commit `bcdc09d`.

## Next Review Batch

Review persona consultation/discussion audit schema ownership.
