# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make `JobMessage` a self-contained typed view of one job envelope instead of a
wrapper with duplicated routing identity.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit request, job, audit, and notification envelope ownership.
2. Specify job routing entirely inside the envelope.
3. Add a strict job payload with resource identity and domain data.
4. Derive `JobMessage.job_id` and `resource_id` from the envelope.
5. Verify envelope record round trips retain all queue routing information.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Keep the durable job manifest authoritative over queue wake-ups.
- Preserve the existing `JobMessage` consumer property API.
- Keep daemon wire frames and durable notification entries in their documented
  ownership models.

## Completion Evidence

- `JobPayload` strictly owns `resource_id` and optional wake-up `data`, rejecting
  missing, blank, non-mapping, or unknown routing fields.
- `JobMessage` now stores only its `RuntimeEnvelope`; `job_id`, `resource_id`,
  and domain payload are derived views over envelope context and payload.
- `JobMessage.create()` embeds every routing value in the envelope, eliminating
  the duplicated wrapper identity and preserving strict JSON immutability.
- Tests prove envelope record round trips retain job/resource routing and data,
  and malformed or duplicate routing fields are rejected.
- Focused runtime-message, reason-output queue, and export-recovery tests:
  `70 passed`.
- `.venv/bin/pytest -q`: `1514 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `6f1d934`.

## Next Review Batch

Audit unused envelope kinds and make the declared message taxonomy truthful.
