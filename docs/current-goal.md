# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — close the Conversation lifecycle durability audit.

## Objective

Verify Conversation lifecycle crash semantics under the SQLite-only authority,
remove obsolete filesystem assumptions, and seal rollback evidence.

## Next Steps

1. Map every lifecycle mutation to locks and SQLite transactions.
2. Add rollback tests for multi-record rename and state transitions.
3. Update the governing specification, stale test vocabulary, and backlog.
4. Run full validation and publish a focused PR to `dev/v0.4.x`.

## Exclusions

- Do not add journaling when one SQLite transaction is already authoritative.
- Do not change pending-turn continuation or replay semantics.
- Do not combine stable Tool operation identity work into this audit.

## Completion Evidence

- Rename cannot leave duplicate old/new identities after rollback.
- Branch/archive/unarchive/delete expose only committed SQLite state.
- Filesystem lock artifacts are documented as coordination, not authority.
- The obsolete cross-directory durability backlog item is removed.
