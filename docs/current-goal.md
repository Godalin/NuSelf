# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Enforce private filesystem permissions at the shared atomic write boundary.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit non-log trace and export persistence paths.
2. Distinguish intentionally preserved private content from diagnostics.
3. Define filesystem permission invariants for NuSelf-owned private artifacts.
4. Enforce those invariants in the shared atomic text/JSON writer.
5. Move internal transcript persistence onto the shared atomic boundary.
6. Verify permissions, atomic failure behavior, and content fidelity.
7. Run full quality gates, commit, and push.

## Out Of Scope

- Trace, transcript, and reason-output content is intentional private domain
  data and is not diagnostically redacted.
- Explicit user-selected exports keep their documented destination semantics.
- Log append, SQLite, and externally selected artifact permissions require
  separate ownership reviews.

## Completion Evidence

- `write_text_atomic(...)` creates or hardens its destination directory to
  `0700`, securely creates each unique temporary file as `0600` before writing
  content, and publishes that mode through atomic replacement.
- Cleanup only removes a temporary file created by the active write; a
  pre-existing name collision remains untouched.
- File-backed trace, reason-output, chat-state, derived-index, scheduler-state,
  and other shared text/JSON persistence inherit the same private boundary.
- Internal transcript export now uses the shared atomic writer while preserving
  the complete intentional transcript content.
- Focused storage, transcript, and trace suites: `21 passed`.
- Full test suite: `1653 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is ready for publication through `6b9a4f8`.

## Next Review Batch

Review SQLite, append-only log, and explicit external-export permission
ownership after atomic private artifacts are protected.
