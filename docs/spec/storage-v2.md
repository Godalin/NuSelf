# Storage

Status: authoritative for v0.3.1.

NuSelf has one structured storage authority per selected scope: SQLite. The
filesystem is used only for configuration, source documents, exports, logs,
runtime coordination, and explicit backups. Runtime code must not implement or
select a second structured-data backend.

## Authority

The selected scope determines the database:

- user scope: `~/.nuself/nuself.sqlite` (or `$NUSELF_HOME/nuself.sqlite`);
- local workspace: `./.nuself/nuself.sqlite`;
- explicit workspace: `<workspace>/.nuself/nuself.sqlite`.

`nuself init` creates an empty, valid database. CLI business entrypoints only
open an existing valid database; readiness rejects a missing database before
repository construction.
An existing empty file, an unrelated SQLite database, an unknown schema, or a
symlinked managed path fails closed. Runtime never falls back to legacy JSON
directories.

Canonical database creation and schema publication are explicit CLI authority
lifecycle operations owned by `nuself init` and approved migration/import
publication paths. A missing database is a typed CLI setup prerequisite, not
an invitation for a business command to create storage.

`scripts/migrate_legacy_layout.py` is the only legacy layout migration tool. Its source
must contain a valid `nuself.sqlite`; it does not import file-backed
collections. Migration takes exclusive source and destination leases, publishes
atomically, and leaves a validated backup. Runtime locks and SQLite sidecars
are transient coordination files: validation and copying ignore them, while
the SQLite backup API captures committed WAL state consistently.

## Storage protocol

Repositories depend on `StorageBackend` and `StorageCollection`:

```python
backend.collection(name)
backend.transaction()

collection.get(key)
collection.put(key, value)
collection.delete(key)
collection.list()
collection.find(**filters)
```

Values are strict JSON objects. A record's `id`, when present, must equal its
storage key. Collection writes replace the complete object. Repository/domain
decoders remain responsible for semantic validation.

Schema v4 introduced one `records` table keyed by
`(collection, id)`. Its strict JSON `payload` omits the redundant `id`; reads
restore it from the primary key. Adding a record field or collection does not
mutate the SQL schema. Namespaced scratch state uses `workspace_entries` in the
same authority database. Runtime code writes rows but never creates or alters
these schema tables.

Both tables are `WITHOUT ROWID`. Schema v5 removes v4's redundant prefix
indexes because the composite primary keys already serve lookups by
`collection` and `namespace`. Exact versioned identity validation checks
the required columns, column order, primary-key order, strict JSON checks, and
`WITHOUT ROWID` definition, plus the version-specific index contract, rather
than accepting tables by name alone.

Before schema v4 can be downgraded, `workspace_entries` must be empty. Operators
first export that state with `scripts/migrate_workspace_layout.py --to legacy
--apply --delete-source`. The v4→v3 migration then drops both compact tables
and recreates only the schema-v3 collection tables; a non-empty workspace
fails inside the migration transaction without publishing schema v3.

All related multi-record changes use `backend.transaction()`. SQLite provides
the commit/rollback boundary; repositories must not retain file-era
compensation logic for operations inside that boundary.

Each `ApplicationRuntime` lazily owns one backend for its canonical authority
and closes it at the CLI/daemon lifecycle boundary. A closed backend and its
collections reject further access. Legacy direct-construction test helpers may
use a pytest-scoped owner that closes selected backends after each test;
production provides no default-backend cache, override, reset API, or global
storage lock.

## Collections

Public/domain collections:

| Collection | Content |
| --- | --- |
| `memory_entries` | durable user-visible memory |
| `memory_candidates` | curator review candidates |
| `profile_items` | structured profile facts |
| `source_documents` | ingested source metadata |
| `source_chunks` | source retrieval chunks |
| `persona_prompts` | persona definitions |
| `conversations` | conversation state and archive status |
| `reason_threads` | long-running reason threads |
| `reason_steps` | reason steps |
| `trace_nodes` | thought traces |
| `trace_edges` | trace links |
| `reflection_entries` | reflection inbox entries |
| `notification_outbox` | notification delivery state |

Internal collections:

| Collection | Content |
| --- | --- |
| `memory_observations` | producer-neutral durable curation inbox |
| `memory_curator_plans` | durable curator plans |
| `scheduler_state` | background scheduler cursors |

Schema migrations may add collections or columns. `_schema_version` records each
completed version exactly once. All schema changes follow
[`database-migrations.md`](database-migrations.md); schema v3 is the historical
baseline, schema v4 is the first strictly reversible migration, and schema v5
is the current compact identity.

## Initialization and upgrades

Managed database paths are validated before chmod, connection, PRAGMA, backup,
or schema work. NuSelf validates the complete managed parent path without
following symlinks. Managed directories use mode `0700`; managed files, schema
locks, and backups use `0600`.

Opening an existing database first performs a lock-aware `mode=ro` identity
check. It checks application/schema metadata and required tables but does not
run `quick_check` on every process start.

The runtime never migrates a database while opening it. A non-current version
fails closed with the explicit `scripts/migrate_database.py` invocation.
That operator-run script uses a stable sibling lock opened with `O_NOFOLLOW`
and an exclusive cross-process `flock`. After acquiring the lease, it rereads
the version, plans a registered adjacent path, creates a pre-migration backup,
and applies the complete path transactionally. The backup retains the old
schema.

External SQLite paths are never treated as managed merely because they are
opened through the library. Their directory and file permissions retain normal
platform/umask semantics, including upgrade locks and backups.

Live databases use ordinary WAL-aware connections. They must not use
`immutable=1`. Normal close performs at most a passive checkpoint; destructive
or truncating checkpoints are restricted to isolated migration/pack workflows.

## Packs, backups, and integrity

Thought-pack export and import operate on explicit SQLite snapshots. Managed
pack destinations receive private permissions. User-selected external paths
retain external permission semantics.

Pack import/inspect and explicit health verification may run
`PRAGMA quick_check`. Ordinary backend open performs metadata identity checks
only, so CLI startup does not become proportional to database size.

Export names and paths must remain within the selected export directory unless
the user explicitly supplies an external output path. Derived paths reject
absolute names, traversal, and symlink escapes.

## User data access

`nuself data` is the generic inspection interface:

```text
nuself data collections [--internal]
nuself data list <collection> [--json] [--internal]
nuself data show <collection> <id> [--json] [--internal]
nuself data export <collection> [--format json|jsonl] [--output PATH]
```

Internal operational collections are hidden unless `--internal` is explicit.

Validated generic mutation is intentionally narrower:

```text
nuself data edit memory|threads <id> [--file PATH | --editor CMD] [--yes]
nuself data delete memory|threads <id> [--yes]
```

Editing starts from the current JSON record, validates the domain schema,
forbids stable identity changes, shows a diff, asks for confirmation, and
compares the original record again inside the transaction. Concurrent changes
fail without overwrite. Successful edits and deletes emit metadata-only audit
events containing the collection and record ID, never the record payload.

Other domain records remain read-only through the generic interface and use
their dedicated commands for mutation.

## Filesystem boundary

These paths may remain files:

- `config.yaml`;
- explicitly ingested source documents;
- JSONL operational logs;
- pack exports/imports and backups;
- PID, socket, and advisory lock files;
- explicit user-requested data exports.

Chat threads, memory, profile, curator state, scheduler state, reasoning,
traces, reflections, and notifications are structured data and therefore live
only in SQLite.
