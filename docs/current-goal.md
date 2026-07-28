# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make optional REPL completion and input-history failures observable without
making the interactive prompt unavailable or losing accepted input.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Classify prompt history, completion, and TTY fallback failures.
2. [x] Specify optional UI best-effort behavior.
3. [x] Route dynamic completion failures through shared observability.
4. [x] Preserve accepted input when history persistence fails.
5. [x] Update user-facing docs/changelog and add focused tests.
6. [x] Run full tests, type checking, and formatting checks.
7. [x] Commit this stage as one functional change.

## Out Of Scope

- Changing command names or completion suggestions.
- Replacing prompt-toolkit or the persisted history format.
- Making completion/history success authoritative to command execution.
- Changing the existing TTY-to-builtin-input fallback conditions.

## Completion Evidence

- Thread, archived-thread, and reason completion failures yield no dynamic
  suggestions and emit a structured degraded event with the exception chain.
- Command-token completion remains available without storage access.
- Builtin input returns the accepted line even if history persistence fails.
- Expected TTY capability failures still fall back to builtin input.
- Focused REPL tests, full pytest, Pyright, and `git diff --check` pass.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue the classified exception audit with remaining domain and storage
cleanup suppression.
