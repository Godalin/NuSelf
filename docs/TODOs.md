# Project Backlog

This file contains unresolved medium- and long-term work only. It is not a
release history or an execution checklist.

- Active work, ordered steps, exclusions, and completion evidence live in
  [`current-goal.md`](current-goal.md).
- Authoritative behavior lives in [`spec/`](spec/).
- Completed user-visible changes live in [`CHANGELOG.md`](../CHANGELOG.md).
- Completed internal work and superseded plans remain available in Git
  history.

Before starting an item, move it into `current-goal.md`, define its governing
specification and completion evidence, and remove it from this backlog in the
same change.

## Memory Retrieval

- [ ] Add derived vector and hybrid retrieval indexes. Treat symbolic graph
  projections separately: the existing graph index remains rebuildable from
  authoritative memory records. Specify the new index lifecycle, fallback
  behavior, and evaluation criteria before implementation.

## Configuration And Distribution

- [ ] Design a configuration management system that composes global user
  configuration with directory-local project configuration. Specify discovery,
  precedence, ownership, secret handling, diagnostics, and migration from the
  current single project-local file before implementation.
- [ ] After configuration discovery is stable, publish supported installation
  flows through PyPI and Homebrew. Define artifact provenance, upgrade and
  uninstall behavior, platform support, and release automation first.

## Reasoning And Notifications

- [ ] Define and implement the long-run reason notification policy. Specify
  which state transitions are user-visible, how notification deduplication and
  quiet hours apply, and how reason events map onto the existing notification
  outbox before implementation.

## Semi-Durable Chat Threads

- [ ] Make ConversationStore lifecycle mutations crash-durable across directories.
  Specify journaling or idempotent recovery for rename/archive/unarchive,
  durable deletion, directory synchronization, and duplicate old/new names
  before strengthening the current semi-durable contract.
- [ ] Remove `ConversationState` constructor index inference for explicit integer
  values. Use a distinct missing sentinel for legacy derivation so internal
  construction rejects inconsistent indexes as strictly as wire decoding.

## Durable Agent Tools

- [ ] Give non-idempotent domain tools stable operation identities independent
  of one chat transport retry. Start with reflection mutations that use
  shifting numeric handles and reason-thread creation/export. Specify replay
  results and domain-level atomicity before considering a persistent LangGraph
  checkpointer; framework checkpoints do not make an already-started external
  side effect exactly-once by themselves.

## Module API Boundaries

- [ ] Execute the ordered remediation in
  [`api-boundary-audit.md`](api-boundary-audit.md): make application resources
  private behind domain facades; replace raw data mutation, reflection's
  concrete cross-domain orchestration, graph-shaped turn projection, hard-coded
  candidate/profile and memory/persona routing, adapter recomposition, weakly
  typed daemon task conventions, and private evaluation construction. Preserve
  the existing single handler/event/log/scheduler infrastructure and avoid a
  general-purpose service bus.

## Test Runtime Hygiene

- [ ] Isolate daemon socket-path adversarial tests under a test-owned temporary
  runtime directory and clean every synthetic socket/file/directory artifact.
  The shared per-user socket runtime must not accumulate fixture endpoints.

## Backlog Rules

- Do not add completed checkboxes.
- Do not use this file for the currently active implementation sequence.
- Keep each item outcome-oriented; detailed behavior belongs in `docs/spec/`.
- When an item becomes active, replace the idle or completed objective in
  `current-goal.md` instead of maintaining two progress boards.
