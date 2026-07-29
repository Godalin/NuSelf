# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make process-local log projection a bounded, composition-validated boundary.
Nested log writes must never recurse through an already-active projection, and
projection failure must remain secondary to the completed durable log append.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory process-local log projection storage, ordering, restoration,
   production callbacks, and failure diagnostics.
2. Reproduce non-callable delayed failure and reentrant logging behavior.
3. Specify bounded synchronous projection, composition validation, and active
   attachment identity semantics.
4. Replace the general observation API and migrate every caller.
5. Prove direct/mutual recursion suppression, duplicate callable identity,
   nested ordering/restoration, failure isolation, and thread non-inheritance.
6. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No asynchronous log projection worker without a concrete production need.
- No compatibility alias for `observe_log_events(...)`.
- No rename of the persisted historical `log_observer_failed` audit identity.
- No change to durable append, fsync, rotation, or retention behavior.

## Completion Evidence

- The only production attachment is request-scoped
  `ActivityBroker.publish`, a bounded in-memory projection.
- Current scope composition accepts non-callables and misreports their delayed
  `TypeError` as a runtime observer failure after a later log append.
- A projection that writes a log immediately receives its own nested record
  again; no active-delivery identity prevents direct or mutual recursion.
- Failure diagnostics already suspend all projections before writing the
  historical `daemon/log_observer_failed` record.
- The public scope API is now `project_log_events(...)`; the old generalized
  `observe_log_events(...)` name was removed without a compatibility alias.
- Scope composition rejects non-callables before any log append.
- Each attachment owns a UUID identity. A separate active-identity
  `ContextVar` skips projections already present anywhere in a nested delivery
  chain while preserving ordered delivery to other attachments.
- Two scopes using the same callable remain distinct attachments rather than
  being incorrectly deduplicated by callable identity.
- Ordinary projection exceptions retain the historical sealed
  `daemon/log_observer_failed` diagnostic; process-control `BaseException`
  values restore active state and propagate after the durable append.
- Production request activity uses the renamed bounded projection boundary.
- Focused log infrastructure, daemon activity, and request-handler tests:
  91 passed.
- Full suite: 2116 passed.
- Pyright: 0 errors, 0 warnings.
- Static search found no old API/type/ContextVar references except the explicit
  no-compatibility statement; `git diff --check` passed.

## Publication

Guarded process-local log projection was implemented in `0434d6f`; milestone
publication is pending this goal update and push.

## Next Review Batch

Review internal message construction next. `RuntimeEnvelope` centralizes
identity, context, version, and JSON-safe payloads, but event, job, and audit
domains still enter it through different validation paths and some sites
construct envelopes directly. Inventory whether invalid producer/name pairs or
domain payloads can exist before ingress, persistence, or projection, and
whether one sealed factory/definition boundary should own construction.
