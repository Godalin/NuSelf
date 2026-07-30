# Database migrations

Status: authoritative for schema changes after SQLite schema v3.

NuSelf database schemas use monotonically increasing positive integer versions.
The application declares one current version and supports only versions for
which the source-checkout migration registry contains a complete adjacent path.
Application code must never perform ad-hoc schema mutation.

## Migration artifacts

Every schema transition is a named migration artifact under
`scripts/database_migrations/` with:

- one stable identifier;
- an exact `from_version` and `to_version`, differing by one;
- an `upgrade(connection)` operation;
- a `downgrade(connection)` operation for every migration introduced after
  schema v3.

Historical migrations that predate this contract may be explicitly
forward-only. A new forward-only migration requires an approved specification
exception and must not be merged merely because implementing reversal is
inconvenient.

The registry rejects duplicate identifiers, duplicate edges, gaps, branching,
and versions beyond the application's declared current schema. Historical
artifacts freeze their exact table and column identities; they must not derive
old schema identity from the runtime's current collection catalog.
The script-owned schema identity registry likewise freezes the required table
set for every supported version. Migration tooling must not call a private
runtime validator, because runtime identity follows only the installed current
schema while migration identity must remain historical.

## Planning and application

A migration request states an explicit target version. The runner reads the
database's current version and constructs the ordered adjacent path:

- ascending edges use `upgrade`;
- descending edges use the same artifacts in reverse order and call
  `downgrade`;
- a missing edge fails before any database mutation;
- a target below the supported floor or above the registered current version
  fails closed.

Normal application startup never migrates in either direction. The storage
backend accepts exactly the current schema version and otherwise fails with the
explicit script invocation required to migrate it. Operators run:

```text
uv run python -m scripts.migrate_database DATABASE --to VERSION --dry-run
uv run python -m scripts.migrate_database DATABASE --to VERSION
```

The first command shows the current version, target version, direction, and
ordered migration identifiers without mutation. Downgrades use the same
explicit interface and fail before mutation when any reverse edge is absent.
Migration code is source-checkout maintenance tooling, not installed as a
NuSelf command and not imported by the NuSelf runtime package.

New databases are created directly at the current schema from the canonical
schema definition. They do not replay historical migrations.

## Safety boundary

The migration script's stable sibling schema lease covers version
revalidation, backup creation, the complete migration plan, and final identity
validation. The runner rereads the version after acquiring the cross-process
exclusive lock.

Before the first mutation, the runner writes one consistent backup of the
original version. Managed databases and artifacts retain NuSelf private
permissions; external paths retain normal platform and umask semantics.

The complete requested path runs in one SQLite transaction. Each successful
edge records its destination version exactly once. Any migration or version
recording failure rolls back the entire path, leaving the original database
version and data intact. A failed migration never publishes a partial target
version.

Migration functions receive the owned SQLite connection. They must not commit,
roll back, change journal mode, open another authority, or acquire their own
schema lease. They must be deterministic and must not depend on network calls,
wall-clock behavior, environment-specific data, or application repositories.

## Version history

`_schema_version` is the authoritative applied-version history. It contains
exactly one row for every completed version from the database's origin through
its current version. Upgrade appends the destination version; downgrade
removes the version being left only after its reverse operation succeeds.

Schema v3 is the compatibility baseline for the strict reversible-migration
policy. Scripted v1→v2 and v2→v3 artifacts preserve upgrades from existing
NuSelf databases; their historical reversibility limits must be declared in
the registry.

## Required verification

Every new migration includes:

- forward fixture tests from the immediately previous version;
- reverse tests and a forward/reverse round trip;
- preservation tests for every affected domain record;
- failure injection proving full transaction rollback;
- concurrent-process tests proving one effective migration;
- backup tests proving the backup retains the original version;
- registry validation and source-checkout invocation tests.

Release compatibility tests migrate the oldest supported schema through every
intermediate version. The compact storage redesign begins at schema v4 and
must be implemented as the first migration governed fully by this contract.
