---
name: reason_proposal
description: Use this skill when the user has explicitly agreed to create a new long-run reasoning thread from the current discussion.
allowed-tools:
  - reason_propose
---

# Reason Proposal Skill

Use this skill only after the user explicitly confirms they want a new
long-running reasoning thread. Do not use it for ordinary questions about
existing reason threads; load the `reason` skill for read-only inspection.

A reason proposal is an information design task. Before calling
{tool:propose}, distill the current discussion into:

- `topic`: the durable question or project the thread should keep thinking
  about. Make it specific enough to identify later.
- `working_summary`: the useful context already established in the discussion,
  including constraints, current assumptions, and why the topic matters.
- `active_items`: initial tracked items. Each item must have a `label`, and may
  include `description` and a free-text `kind` such as `hypothesis`,
  `character`, `suspect`, `plot_thread`, `world_rule`, `risk`, or `decision`.
- `mandates`: required actions the advancer must follow on every advance.
  Mandates are architectural constraints, not suggestions. Ask the user before
  adding mandates.

For simulations, debates, interviews, games, or staged discussions, include a
pacing mandate such as "advance at most one complete round per step" unless the
user explicitly wants larger batches. If the task has setup work, say whether
setup is separate or may happen before the first round.

Before proposing, consider whether the thread needs additional context from
memory, trace, selves, or persona tools. Use the relevant skill first if that
context is needed.

Call {tool:propose} only after the user has already said yes. The CLI will ask
for final confirmation once more before the thread is actually created.
