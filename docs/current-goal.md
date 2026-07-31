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

- Steps 1–2 complete: the governing contracts now define inert orthogonal
  declarations, and the immutable tool specification plus LangChain registrar
  are implemented with focused tests.
- Step 3 in progress: confirmation, observation, and audit execution ports are
  implemented and tested; production adapters and existing tools remain to be
  migrated.

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

## Progress

- Steps 1-2 foundation complete: governing specs now define the compact
  module, frontend-event, and orthogonal policy contracts; immutable tool,
  component, effect, confirmation, observation, and audit decorators plus the
  LangChain materializer have focused tests and pass Pyright.
- Step 3 in progress: shared execution already consumes injected approval,
  frontend-event, clock, and audit ports; existing tools and terminal/daemon
  adapters still need migration before the legacy approval implementation can
  be removed.
