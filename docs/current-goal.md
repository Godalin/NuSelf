# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Idle — no active implementation goal.

## Objective

No active objective.

## Next Steps

1. Wait for the next explicitly approved goal.

## Exclusions

- Do not begin unapproved feature or refactor work.

## Last Verification

- Same-domain forwarding capabilities are folded into their domain Service;
  independent domain, projection, workflow, job, and adapter boundaries remain
  separate.
- `MemoryService` owns candidate review and `ApplicationGraph` exposes no
  parallel candidate Service.
- Persona exposes one method vocabulary without compatibility aliases.
- Production Service classes live in single-word modules; the historical API
  audit document has been removed.
- `uv run --locked pytest`: 2,337 passed.
- `uv run --locked pyright`: 0 errors, 0 warnings.
- `git diff --check`: passed.
