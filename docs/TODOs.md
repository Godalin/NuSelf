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

## Reasoning And Notifications

- [ ] Define and implement the long-run reason notification policy. Specify
  which state transitions are user-visible, how notification deduplication and
  quiet hours apply, and how reason events map onto the existing notification
  outbox before implementation.

## Semi-Durable Chat Threads

- [ ] Make ThreadStore lifecycle mutations crash-durable across directories.
  Specify journaling or idempotent recovery for rename/archive/unarchive,
  durable deletion, directory synchronization, and duplicate old/new names
  before strengthening the current semi-durable contract.
- [ ] Remove `ThreadState` constructor index inference for explicit integer
  values. Use a distinct missing sentinel for legacy derivation so internal
  construction rejects inconsistent indexes as strictly as wire decoding.

## Backlog Rules

- Do not add completed checkboxes.
- Do not use this file for the currently active implementation sequence.
- Keep each item outcome-oriented; detailed behavior belongs in `docs/spec/`.
- When an item becomes active, replace the idle or completed objective in
  `current-goal.md` instead of maintaining two progress boards.
