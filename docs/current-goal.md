# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make the declared `RuntimeEnvelope` kind taxonomy match the messages the
runtime actually produces and consumes.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Trace every declared kind to a concrete producer and consumer.
2. Document transport and durable records that deliberately do not use an
   envelope.
3. Remove unimplemented request and notification kinds.
4. Reject those kinds in local construction and strict record decoding.
5. Verify event, job, and audit remain the complete supported taxonomy.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Keep daemon request/response framing under `daemon.protocol`.
- Keep notification correlation on the durable outbox entry.
- Do not add placeholder kinds for possible future transports.

## Completion Evidence

- `MessageKind` and the runtime decoder now accept exactly `event`, `job`, and
  `audit`, each backed by a concrete producer and consumer.
- Dormant `request` and `notification` kinds were removed; daemon frames remain
  owned by `daemon.protocol`, while notification correlation remains on the
  durable outbox entry.
- Local construction and strict record decoding both reject the removed kinds.
- Tests round-trip the complete supported taxonomy and cover the independent
  daemon protocol and notification ownership paths.
- Focused runtime-message, event, log, protocol, and notification tests:
  `140 passed`.
- `.venv/bin/pytest -q`: `1519 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `bfc0912`.

## Next Review Batch

Audit whether audit envelopes should become a first-class typed projection.
