# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active.

## Objective

Simplify the runtime kernel while preserving feature depth: make feature
modules independently composable, express cross-cutting tool behavior through
orthogonal decorators, and separate interactive frontends from backend
execution through typed events so terminal, daemon, and future web adapters can
present the same activity without backend presentation dependencies.

## Ordered Steps

1. Specify compact module, decorator, execution-policy, and frontend-event
   contracts.
2. Implement immutable orthogonal feature metadata and decorators without
   introducing a parallel agent-tool protocol.
3. Execute confirmation, observation, and audit policies through shared
   middleware with injected ports rather than terminal I/O in tool functions.
4. Project backend activity into typed frontend events and adapt the existing
   terminal UI to those events.
5. Migrate existing tools and remove superseded factories, decorators, and
   presentation imports.
6. Collapse redundant application composition wrappers and prove that a new
   module needs one local implementation plus one composition registration.
7. Run architecture tests, unit tests, Pyright, build, clean-wheel smoke, and
   the final six-platform CI.

## Progress

- Steps 1–6 implemented locally. All framework tools now use the single
  declarative materializer; confirmation uses an injected frontend port;
  observation and approval activity project through the existing typed
  `chat/tool.activity` event; terminal input lives only in the TUI adapter; and
  the old factories, effectful approval wrapper, and parallel approval-audit
  path are removed.
- Conversation composition now passes two ownership-specific inert resource
  snapshots (`ConversationResources` and nested `ToolResources`). Executable
  architecture tests enforce the only LangChain materializer, backend/TUI
  direction, and bounded runtime constructor fan-in.
- Step 7 in progress: Pyright reports 0 errors and 0 warnings; all 2487 tests
  pass; sdist and wheel builds succeed; and a clean Python 3.12 environment
  imports the wheel and runs `nuself --version`. Commit, push, and final
  six-platform CI remain.

## Exclusions

- No dynamic third-party plugin loading in this goal.
- No replacement for LangChain/LangGraph tool dispatch.
- No generic bus merging requests, events, jobs, audits, and notifications.
- No compatibility layer for superseded internal composition APIs.

## Completion Evidence

- Tool functions compose independent decorators for identity, component,
  effects, confirmation, observation, and audit.
- Decorators contain no terminal input, rendering, persistence, or transport.
- CLI and daemon presentation consume typed frontend events through adapters;
  backend modules do not import `nuself.tui`.
- Existing chat tools use the new path and old approval/factory wrappers are
  absent.
- Architecture tests enforce frontend/backend direction and module-local
  extension.
- Full local and six-platform release gates pass.
