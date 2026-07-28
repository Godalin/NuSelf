# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Validate each runtime event exactly once against the immutable payload that
subscribers actually receive.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit event definition resolution, envelope creation, and delivery.
2. Identify duplicate validation across `publish` and `publish_envelope`.
3. Validate the canonical frozen envelope payload once.
4. Deliver through a private already-validated path.
5. Verify validator count, payload identity, and direct-envelope validation.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Unknown event definitions still fail before envelope delivery.
- Existing envelopes remain validated before delivery.
- Subscriber snapshot, order, isolation, and failure aggregation remain
  unchanged.

## Completion Evidence

- `publish(...)` resolves the definition, constructs the immutable envelope,
  validates `event.payload` once, then enters an already-validated delivery
  method.
- `publish_envelope(...)` validates its immutable payload once and uses the
  same delivery method.
- Tests prove validator and subscriber observe the exact same payload object,
  including canonical tuple conversion for a caller-provided list.
- Existing unknown-definition, invalid-payload, subscriber order/isolation,
  lifetime handle, and failure aggregation behavior remains covered.
- Focused runtime event, message, and observability tests: `73 passed`.
- `.venv/bin/pytest -q`: `1615 passed` with no warnings.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `1c9cd14`.

## Next Review Batch

Continue reviewing internal-message subscription and delivery lifecycle after
canonical validation is unified.
