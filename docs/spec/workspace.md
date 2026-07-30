# Private Workspace Spec

## Purpose

Private workspaces provide isolated, task-local scratch storage for agent-facing services.

They are meant for internal working state that is useful while a subsystem is operating but not yet stable enough to become memory, trace, source material, or user-facing output.

## Storage Contract

Structured workspace identity:

```text
<authority-root>/nuself.sqlite
  workspace_entries namespace: workspace/{scope}/{owner_id}
```

- `scope`: service namespace, e.g. `reason`.
- `owner_id`: service-owned object id, e.g. a reason thread id.
- Generated user-facing files live under
  `<authority-root>/exports/{scope}/{owner_id}/`.

## Isolation Rules

- A workspace belongs to one service scope and one owner id.
- Services must not directly read or write another service's workspace.
- Agents and subsystems should access workspace state through the owning service or tool-facing adapter.
- Workspace contents are not authoritative global state.
- Workspace data must not bypass promotion rules for memory, trace, source ingestion, or reason steps.
- Archiving a service object must not silently delete its workspace; cleanup should be explicit.

## SQLite Contract

Workspace values use the shared strict JSON encoder before SQL mutation.
Non-string keys, arbitrary objects, and non-finite floats are rejected.
`SqliteStore.batch()` owns one transaction: if any operation cannot encode,
all earlier writes from that batch are rolled back and pre-existing entries
remain unchanged. Reads reject non-standard non-finite JSON constants.
Each batch owns exactly one short-lived SQLite connection and closes it exactly
once. Schema creation belongs only to authority initialization or an explicit
database migration. A successful batch commits before closing; a failed batch rolls back
before closing. If rollback or close also fails, the store must retain every
failure without replacing the original operation error as the explicit cause.
Close failure after a successful commit is still surfaced, without replaying
the committed batch.

Repository-shaped scratch state uses a `ScopedWorkspace` collection adapter
over `SqliteStore`; it must not introduce a second raw-file repository
protocol or derived name-index files.

## Reason Usage

Reason uses:

```text
<authority-root>/nuself.sqlite
namespace workspace/reason/{thread_id}
```

The reason workspace can hold branch tables, temporary tracked items, local evidence indexes, tool results, scratch rankings, intermediate plans, and failed-path records.
Reason-thread persona prompts are stored under the thread workspace's
`persona_prompts` namespace in SQLite. They are task-local scratch state, not
durable global persona records. The explicit v4 layout migration imports
legacy per-thread SQLite workspace entries before retiring the old tree.
All reason workspace consumers use the canonical
`("workspace", "reason", thread_id)` namespace prefix.

The source-checkout `scripts/migrate_workspace_layout.py` command is the only
supported bridge from `<authority-root>/workspaces/reason/*/workspace.sqlite`.
It defaults to dry-run, validates each workspace identity and JSON row, copies
all rows in one main-authority transaction, and verifies export-file
destinations before copying. `--apply --delete-source` moves the verified old
tree to `backups/legacy-workspaces-v3`; it never silently deletes it. Runtime
startup never scans, imports, or deletes the old tree.

Stable data leaves the workspace only through explicit promotion:

- reason steps for user-readable reasoning updates;
- trace records for provenance;
- memory candidates or source ingestion for durable reusable knowledge.

## Future Service Usage

Private workspaces are generic. Reason is the first user, but future service scopes may include:

- `reflection`: candidate organization, clustering, or merge-analysis scratch state.
- `trace`: temporary graph exploration and provenance query caches.
- `tool`: long-running tool worker state for complex tasks.
- `nusolang`: future cognitive workflow runtime state.

Each scope must define its owner id, service-facing API, cleanup policy, and promotion rules before writing workspace data.
