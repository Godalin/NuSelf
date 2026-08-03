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

- Inbox now owns durable user-attention items and source-domain references;
  Delivery independently owns adapter plans and results.
- Reflection always publishes an Inbox item; meaningful non-`no_change` Reason
  steps publish one; optional external delivery remains independently tracked.
- Old Notification source, nested commands, fixtures, and installed package
  paths are removed; `scripts/inbox.py` previews/applies legacy data migration.
- The project-local config uses `daemon.delivery`; its database contained zero
  legacy Notification records and `nuself --local inbox` starts successfully.
- `uv run --locked pyright`: 0 errors, 0 warnings.
- `uv run pytest -q`: 2329 passed.
- `uv build`: source distribution and wheel built successfully.
