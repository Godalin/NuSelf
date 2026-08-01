# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — close scheduler and feature-policy correctness gaps found by external
review.

## Objective

Preserve the single daemon scheduler and simple application composition while
eliminating dispatcher spinning, post-commit chat ambiguity, dead-scheduler
fallback behavior, inert observation declarations, and unsafe/stale scheduler
health errors.

## Ordered Steps

1. Make dispatcher waiting resource- and capacity-aware, with regression tests
   proving blocked work sleeps until notification.
2. Treat durable chat commit/projection as primary and follow-up admission as
   recoverable wake-up; add durable compression discovery.
3. Execute `@observed` lifecycle policy centrally in `FeatureExecutor`.
4. Fail closed when daemon scheduling is unavailable and sanitize scheduler
   failure health.
5. Minimally type production task construction, reconcile the audit document,
   run all gates, commit, push, and verify CI.

## Exclusions

- No service bus, per-domain scheduler, persistent generic queue, or new lock
  hierarchy.
- No ApplicationResources/ApplicationServices duplication in this goal.
- No one-method facade or compatibility fallback.

## Completion Evidence

- Scheduler blocked-state tests cannot observe zero-timeout spinning.
- A committed chat reply remains successful when follow-up admission closes;
  durable recovery later discovers both curation and compression work.
- Observed functions publish started/completed/failed, while undecorated
  functions publish none.
- Dead scheduler chat fails before model execution; health exposes only
  payload-safe current degradation state.
- Pyright, full pytest, build, clean-wheel smoke, and final CI pass.
