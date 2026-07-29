# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make bounded daemon activity delivery loss-aware. Queue overflow must be
represented in the protocol and force the interactive client onto persisted
turn-scoped log recovery instead of silently presenting an incomplete stream.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory activity queue overflow, protocol payloads, client polling,
   cursor de-duplication, and fallback tests.
2. Update runtime-infrastructure, CLI, log, and protocol contracts first.
3. Track dropped events per subscription and return an exact non-negative count
   with each activity batch.
4. Raise a typed client-side stream-gap failure before presenting a partial
   batch.
5. Reuse the existing degradation audit and persisted turn-scoped cursor
   fallback without replaying already delivered event identities.
6. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No unbounded activity queue.
- No retry or replay of chat commands.
- No change to authoritative log persistence or retention.
- No cross-turn recovery; fallback remains scoped to the active `turn_id`.

## Completion Evidence

- Loss-aware activity delivery completed in `699a46e`.
- Each subscription tracks exact evictions since its previous read.
- `ActivityEventsResponsePayload` requires exact `events` and non-negative
  integer `dropped_count` fields; booleans and missing/invalid counts fail
  protocol decoding.
- `ActivityStreamGapError` retains the dropped count and enters the existing
  application-degradation recovery path before a partial batch is presented.
- Focused activity/protocol/transport/REPL tests: 78 passed.
- Full suite: 2082 passed.
- Pyright: 0 errors, 0 warnings.
- `git diff --check`: passed.

## Publication

Activity stream-gap recovery was implemented in `699a46e`; milestone
publication is pending this goal update and push.

## Next Review Batch

Review `EventPublisher` subscription ownership next. Named subscriptions
currently filter only by event name even though definitions are keyed by
producer and name; determine whether producer-blind subscriptions can leak
same-named events across subsystem boundaries, then make subscription selectors
match the registered event identity rather than a partial string when needed.
