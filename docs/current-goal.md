# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

In progress — converge Storage infrastructure ownership.

## Objective

Replace the three flat top-level Storage modules with a compact
`nuself.storage` package. Separate contracts, atomic filesystem writes,
authority lifecycle, SQLite persistence, thought-pack operations, and audit;
migrate every caller without compatibility forwarding modules. Move the
top-level LangGraph `store.py` adapter under the same package as `workspace`.

## Next Steps

1. Split contract, atomic, authority, and audit owners; migrate their callers.
2. Separate the SQLite backend from thought-pack validation and exchange.
3. Audit remaining responsibilities and old paths.
4. Run full Pyright, pytest, and build gates; commit complete boundaries,
   return this file to Idle, and stop.

## Exclusions

- Preserve database schemas, collection names, authority selection, migration
  and backup semantics, path hardening, file permissions, and CLI behavior.
- Do not introduce a second backend, public facade, service locator, generic
  `model.py`, or compatibility import shim.
- Do not split helpers that are inseparable from their sole owner merely to
  make files shorter.

## Last Verification

- Baseline before this goal: Pyright 0 errors and 0 warnings; full pytest and
  NuSelf 0.3.1 source/wheel builds passed.
- Initial audit: `storage.py` mixes contracts, collection catalog, atomic file
  writes, and authority lifecycle; `storage_sqlite.py` mixes the live backend
  with thought-pack exchange; `storage_audit.py` is already a cohesive owner.
- Contract/atomic/authority/audit split: every caller now imports a precise
  owner from `nuself.storage`; no package-root facade exists. Full Pyright
  reports 0 errors and 0 warnings.
- The former top-level `store.py` is the LangGraph `BaseStore` adapter over the
  same database's `workspace_entries` table; it now belongs to
  `storage.workspace`, together with private workspace path resolution, rather
  than a second top-level storage concept. 256 focused storage, workspace,
  composition, Agent, Reason, notification, and conversation tests pass.
