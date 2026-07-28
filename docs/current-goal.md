# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Stop CLI chat-timeout and history helpers from hiding unexpected configuration
or persisted-thread failures.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Trace timeout configuration and history state loading behavior.
2. [x] Correct config and CLI error-boundary specifications.
3. [x] Remove the redundant broad timeout-config fallback.
4. [x] Distinguish empty history from corrupt or unreadable thread state.
5. [x] Update user-facing docs/changelog and add focused tests.
6. [x] Run full tests, type checking, and formatting checks.
7. [x] Commit this stage as one functional change.

## Out Of Scope

- Changing YAML fallback behavior for expected read/parse failures.
- Changing the configured or default daemon chat timeout values.
- Repairing or quarantining corrupt thread files automatically.
- Changing prompt-toolkit completion degradation in this commit.

## Completion Evidence

- Missing or malformed YAML retains its documented default behavior.
- Unexpected config loader failures propagate instead of silently choosing 120s.
- Missing/empty thread history still renders the existing empty message.
- Corrupt or unreadable history renders a concise exception-chain diagnostic.
- Focused CLI tests, full pytest, Pyright, and `git diff --check` pass.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue the classified exception audit with optional completion and terminal
input degradation.
