# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active.

## Objective

Review the complete chat path for lean module boundaries and verify that
post-turn memory processing is robust under retries, failures, concurrency,
and interrupted clients. Fix confirmed issues with the smallest coherent
design.

## Ordered Steps

1. Map ownership and data flow across the turn graph, model/tool loop, thread
   persistence, compression, trace recording, and post-turn curation.
2. Verify dependency direction and identify duplicated orchestration or hidden
   authority selection.
3. Verify curator idempotency, transaction boundaries, retry behavior, failure
   isolation, concurrency control, and recovery evidence.
4. Reproduce confirmed weaknesses with focused tests.
5. Update governing specs before behavioral changes, implement minimal fixes,
   then run full local and six-platform gates.

## Confirmed Findings

- Daemon chat synchronously runs a second model-backed curator pass before it
  returns an already-persisted reply, even though a curator worker already
  exists. This duplicates scheduling authority and adds avoidable chat latency.
- Both daemon post-chat curation and the periodic worker omit the active thread
  ID, so non-default conversations incorrectly curate `default`.
- The minimal correction is one worker-owned pending-thread set plus periodic
  enumeration for recovery; no generic queue or new worker framework is needed.
- Stable `turn_id` reuse accepted different input and reran the model/tool loop;
  it now fails before execution.
- Chat state reconstruction dropped the persisted archived flag; update and
  compression now preserve it.
- A remaining reliability boundary needs explicit treatment: a mutating tool
  can commit before the final thread save. If that save fails, no completed
  turn record exists to prevent a client retry from invoking the mutation
  again. Endpoint retry suppression only protects the current agent invocation
  and does not close this cross-request commit gap.
- The outer four-node `StateGraph` supplied no routing, checkpoint, interrupt,
  or recovery behavior and duplicated the real `create_agent` graph. It has
  been reduced to a direct typed NuSelf pipeline while the framework retains
  ownership of the model/tool loop.

## Exclusions

- No speculative framework or new generic abstraction.
- No redesign justified only by naming or file size.
- No unrelated storage, notification, or UI work.

## Completion Evidence

- Every chat and post-chat stage has an explicit owner and authority source.
- Retry and concurrent execution cannot duplicate committed turns or memory
  mutations.
- Secondary compression, trace, and curator failures have documented and tested
  effects on the primary reply and persisted state.
- Architecture and behavior tests cover the conclusions.
- Full local and six-platform gates pass after any code changes.
