# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make daemon PID metadata atomically published and observably decoded so
malformed lifecycle state cannot silently appear identical to a stopped daemon.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Audit PID publication, status reads, and stop escalation use.
2. [x] Specify missing, malformed, and unreadable PID semantics.
3. [x] Add one shared atomic text writer and publish the owner PID through it.
4. [x] Accept only a positive base-10 integer after surrounding whitespace.
5. [x] Report empty, non-integer, zero, and negative PID files through the
   shared payload-safe corruption boundary, then return no PID.
6. [x] Preserve propagation for non-missing filesystem failures.
7. [x] Run focused/full tests, type checking, and formatting checks.
8. [x] Update user-facing docs/changelog and commit this stage.

## Out Of Scope

- Changing daemon instance-lock or socket ownership behavior.
- Verifying PID process identity through `kill(pid, 0)` or process metadata.
- Automatically deleting a malformed PID file.
- Changing CLI start polling duration or stop escalation policy.

## Completion Evidence

- Missing PID state returns `None` without a warning.
- A valid positive PID round-trips through atomic owner publication.
- Empty, non-integer, zero, and negative content each returns `None` and emits
  one `record_decode_failed` event without echoing file contents.
- Directory, permission, and other non-missing read failures propagate.
- Failed atomic publication leaves no partial destination or temporary file.
- Focused lifecycle/storage tests, full pytest, Pyright, and
  `git diff --check` pass.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit daemon start/stop polling and PID-to-process identity assumptions.
