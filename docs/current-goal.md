# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close the v0.3.0 concurrency, credential, configuration, and release-safety
findings identified by external audit.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Make shared SQLite reads and metadata operations transaction-isolated,
   invalidate dynamic schema state across processes, and reject record-ID
   mismatches.
2. Fence File-to-SQLite authority migration against active file-backed
   runtimes and protect external `--db` parent permissions.
3. Serialize notification delivery per entry, unify adapter composition, and
   represent crash-after-send uncertainty without automatic duplicate sends.
4. Remove SMTP/config credential exposure, eliminate the email configuration
   split, and harden the private root and secret files before reads.
5. Make runtime config validation and JSON Schema strict and equivalent.
6. Align health and daemon configuration-restart reporting with the config
   lifecycle.
7. Run the complete multithread, multiprocess, rollback, crash-injection,
   compatibility, type, build, and clean-wheel release gates.

## Out Of Scope

- The future global plus directory-local configuration layering system.
- PyPI, Homebrew, or other package-manager publication.
- A release tag until every v0.3.0 gate is proven and the release commit is on
  `main`.
- Existing documented semi-durable ThreadStore follow-ups.

## Completion Evidence

- SQLite connection operations now share one reentrant lock, dynamic schema
  reads do not retain stale process-local caches, and SQLite `put` rejects
  mismatched record IDs. Commit-level verification: 68 SQLite tests passed,
  including blocked-read commit/rollback cases and dual-backend schema
  mutation; locked Pyright reported 0 errors and 0 warnings.
- File backends now hold shared lifecycle authority leases and migration holds
  the exclusive cross-process lease through publication. External `--db`
  destinations fail before filesystem mutation. Commit-level verification:
  78 storage/migration/CLI tests passed, including a spawned active-runtime
  fence and external-mode preservation; locked Pyright reported 0 errors and
  0 warnings.
- Notification entries now use stable cross-process delivery locks and persist
  `delivering` before adapter effects; recovered in-flight states become
  terminal `uncertain` without replay. Commit-level verification: 348
  notification/CLI regressions passed, plus spawned-process tests proved one
  external effect and dismiss serialization; locked Pyright reported 0 errors
  and 0 warnings.
- Configuration models now reject unknown fields, hide validation inputs, and
  match the published JSON Schema across every section and numeric constraint.
  API keys and SMTP passwords are repr-safe and generically redacted; config
  reads reject symlinks and harden `private/`/`config.yaml`. Email now consumes
  the unified YAML model with an explicit recipient, and daemon/CLI/REPL share
  one adapter builder. Commit-level verification: 438 focused config,
  notification, daemon, and CLI tests passed; locked Pyright reported 0 errors
  and 0 warnings.
- Pending: the remaining external findings need implementation and direct
  regression evidence, followed by the complete stable-release gate.
