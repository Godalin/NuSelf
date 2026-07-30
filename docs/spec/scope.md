# Runtime Scope And Authority Spec

## Concepts

Every NuSelf invocation resolves exactly one `NuSelfScope` before loading
configuration, opening storage, writing logs, or contacting a daemon.

| Scope kind | Selection | Authority root |
|---|---|---|
| User | default | `$NUSELF_HOME` when set, otherwise `~/.nuself` |
| Workspace | `--local` | `$PWD/.nuself` |
| Workspace | `--workspace PATH` | `<canonical PATH>/.nuself` |

`--local` and `--workspace` are mutually exclusive. `NUSELF_HOME` changes only
the user authority root; it does not select workspace scope. NuSelf does not
discover `.nuself` directories in parents and does not switch scope merely
because one exists in the current directory.

The canonical authority root determines a stable `authority_id`. The ID is a
versioned cryptographic digest of the canonical root, suitable for filenames
and protocol comparison. Selecting the same root through different explicit
means identifies the same authority. The ID is an identity, not a secret.

## Resolved Paths

Path selection occurs once at a composition root. Domain modules receive the
resolved scope, `RuntimePaths`, repositories, or storage boundaries; they do
not inspect the current directory, home directory, environment, or repository
markers independently.

Each authority owns:

```text
<authority-root>/
  config.yaml
  nuself.sqlite
  sources/
  logs/
  exports/
  imports/
  runtime/
```

User and workspace authorities have the same internal layout. The source
checkout is neither an install root nor an implicit authority.

Runtime paths include the selected scope, authority ID, configuration files,
database, source/import/export directories, logs, and daemon lifecycle paths.
Managed authority roots and files retain NuSelf's no-follow and owner-only
filesystem protections.

## Configuration Layers

Configuration and persisted state have deliberately different semantics.

Effective configuration is merged in this order:

```text
built-in defaults
< user config
< workspace config
< explicitly supported environment or CLI value
```

For user scope, the selected authority config is the user config and is read
once. For workspace scope, `~/.nuself/config.yaml` (or the `NUSELF_HOME`
equivalent) supplies user defaults and the selected workspace
`config.yaml` overrides them.

Mappings merge recursively. A present scalar or sequence replaces the lower
layer. The final merged mapping is validated once through the published typed
configuration model. Diagnostics identify the layer containing malformed YAML
or an invalid value without exposing secrets.

Configuration layering does not layer runtime state. SQLite, memory, threads,
profile, persona, reason, trace, reflection, notification, logs, and derived
runtime preferences read and write only the selected authority.

## Initialization

`nuself init` initializes the selected user authority. `nuself init --local`
and `nuself init --workspace PATH` initialize the corresponding workspace.
Initialization:

- creates only the selected managed authority tree;
- refuses symlinked or non-directory authority components;
- does not create a database unless the storage initialization contract
  explicitly publishes a valid NuSelf authority;
- is idempotent when the existing layout is valid;
- does not overwrite an existing config or database.

Ordinary read-only inspection does not silently create an authority tree.
Commands that require durable writes may report that initialization is
required rather than creating unrelated directories.

`nuself dev paths` reports the scope kind, canonical authority root,
authority ID, effective configuration layers, database, logs, runtime
resources, and daemon identity. Secrets are never included.

## Daemon Isolation

Each authority has an independent daemon instance with its own:

- exclusive instance lock;
- PID and lifecycle metadata;
- Unix socket;
- SQLite authority;
- background scheduler and notification outbox.

Socket paths must remain below platform Unix-domain socket length limits.
NuSelf may place sockets in a short, owner-private runtime base and name them
by `authority_id`; metadata records the canonical authority root. Persistent
logs and state remain in the authority root.

Every daemon request/response handshake carries the authority ID. A client
must reject a responsive daemon whose authority ID differs from the selected
scope. Starting, stopping, restarting, or inspecting one daemon cannot mutate
another authority's lifecycle resources.

## Legacy Layout Migration

The v0.3.0 checkout-local layout:

```text
<legacy-root>/private/
```

is never an implicit v0.3.1 authority. Detection may print a migration hint,
but must not copy, merge, rename, delete, chmod, open, or upgrade legacy data.

An explicit migration command selects one source and one target:

```text
nuself migrate-layout --from PATH --to user
nuself migrate-layout --from PATH --to-local
nuself migrate-layout --from PATH --workspace PATH
```

Migration runs under an exclusive target lease, validates the source before
publication, refuses a non-empty or conflicting target, and publishes a
complete target atomically where the filesystem permits. Failure preserves
the source and leaves no partial authority. Success also preserves the source
unless a future separately approved command adds destructive cleanup.

Configuration is copied as configuration, SQLite as its single authority, and
managed non-database artifacts into their corresponding target paths. It is
never valid to combine legacy and new storage as parallel authorities.

## Explicit Exclusions

v0.3.1 does not provide:

- implicit workspace discovery;
- combined user/workspace memory search;
- cross-authority references or write routing;
- local tombstones that hide user records;
- one daemon multiplexing multiple authorities;
- arbitrary named profiles.
