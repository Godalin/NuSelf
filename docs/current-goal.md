# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Use one safe exception presentation boundary across the entire CLI package.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit every remaining direct exception rendering site.
2. Separate CLI presentation from domain decision and wrapping logic.
3. Define the CLI safe exception presentation contract.
4. Migrate chat, REPL, transcript, and command adapters together.
5. Preserve exit codes, retry metadata, stream routing, and original failures.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Agent-tool and background-domain fallback text is reviewed separately after
  the CLI package is complete.
- Already-decoded daemon application error strings remain protocol-owned text.
- Successful output and user-supplied arguments are never globally sanitized.

## Completion Evidence

- Every caught exception rendered or projected inside `nuself.cli` now uses
  `diagnostic_exception_message(...)`; source audit finds no direct
  `str(exception)` or f-string exception rendering.
- Daemon and one-shot chat preserve retry metadata, exit codes, stderr routing,
  and audit ownership while sanitizing caught connection/runtime failures.
- REPL command handlers, dispatcher output, transcript/export helpers, visible
  handles, daemon/reflection/thread/reason/pack commands, and all memory command
  modules share the same presentation boundary.
- An AST architecture test rejects future direct rendering of an
  `except ... as name` variable anywhere in the CLI package.
- Behavior tests prove credentials are absent from CLI stderr and audit records
  and a broken runtime exception renderer falls back to its class name.
- Focused CLI, entrypoint, REPL, and transcript suites: `317 passed`.
- Full test suite: `1645 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `56ef7d5`.

## Next Review Batch

Review agent-tool and background-domain fallback text after CLI exception
presentation is centralized.
