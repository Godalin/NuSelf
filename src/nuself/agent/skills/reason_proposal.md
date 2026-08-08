---
name: reason_proposal
description: Use this skill when the user has explicitly agreed to create a new long-run reasoning thread from the current discussion.
allowed-tools:
  - reason_propose
---

# Reason Proposal Skill

Use this skill when the user wants to start a new long-running reasoning
thread. Do not use it for ordinary questions about existing reason threads;
load the `reason` skill for read-only inspection.

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

If the thread uses explicit personas as debate participants, interviewees,
reviewers, judges, or staged speakers, include a persona-grounding mandate:
persona_craft may create local personas, but every later persona utterance,
answer, critique, vote, judgment, or dialogue line must come from persona_think
in the same advance. Do not propose a persona-driven thread where the advancer
is expected to invent local persona speech directly in output.

Before proposing, consider whether the thread needs additional context from
memory, trace, selves, or persona tools. Use the relevant skill first if that
context is needed.

Call {tool:propose} once the user has expressed the intent to start the
thread. Call `reason_propose` only after the user explicitly confirms they
want to start the thread. The decorated tool wrapper will prompt for
confirmation before writing the proposal; the CLI may still surface the
resulting `proposal_created` event as an audit log, but it should not ask for
a second confirmation.

Supply a stable, non-secret `operation_id` for the logical proposal and reuse
it if that same proposal is retried. Do not use a request id, turn id, or tool
call id. A short descriptive token such as `reason-career-tradeoff-2026-08`
is sufficient; a different proposal must receive a different operation id.

Tool return values: The decorated proposal tool returns a structured JSON
string that preserves the underlying callable's result while indicating the
user approval state. Example formats:

- On approval and creation:

```
{"approved": true, "component": "reasoning", "approver": "<user>", "result": "<thread_id>"}
```

- On cancellation:

```
{"approved": false, "component": "reasoning", "result": null}
```

The `result` field contains the original return value from `reason_propose`
(the created thread id) when present.
