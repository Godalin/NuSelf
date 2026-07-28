# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Route runtime secondary logging and durable-job wake-up failures through the
shared observable best-effort boundary.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Classify remaining silent and broad exception handlers.
2. [x] Specify best-effort behavior for persona audit and job wake-up failures.
3. [x] Migrate chat persona secondary logs to shared observability.
4. [x] Preserve export wake-up exception chains without losing durable jobs.
5. [x] Add focused failure-path tests.
6. [x] Run full tests, type checking, and formatting checks.
7. [x] Commit this stage as one functional change.

## Out Of Scope

- Changing persona consultation or competitive discussion policy.
- Making audit logging authoritative for a successful persona operation.
- Replacing the durable export manifest or in-memory wake-up transport.
- Mechanically removing intentional not-found, cleanup, or decode isolation.

## Completion Evidence

- Persona results survive audit sink failure while the failure remains visible.
- Discussion failures still degrade to a result if their failure log also fails.
- Export manifests remain durable and non-terminal when queue wake-up fails,
  and the compact exception chain is observable.
- No local broad logging wrapper remains in the migrated paths.
- Focused failure tests, full pytest, Pyright, and `git diff --check` pass.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue the classified exception audit with agent structured-output fallback
and CLI configuration/history boundaries.
