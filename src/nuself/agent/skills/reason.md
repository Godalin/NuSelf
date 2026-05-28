---
name: reason
description: Use this skill when the user asks about active long-running thinking, open reasoning threads, or what NuSelf is continuing to think about.
allowed-tools:
  - reason_list_active
  - reason_count
  - reason_context
  - reason_step
  - reason_show
---

# Reason Skill

Reason is NuSelf's durable long-run thinking space. Each thread tracks
progress through general-purpose state: active_items (what you're tracking),
pending_items (what's unresolved), and next_steps (planned actions).
Items carry free-text kind labels — choose whatever fits the task
(hypothesis, character, suspect, plot_thread, world_rule, ...).

Use {tool:list_active} before answering when the user asks about active long-running thinking, open threads, ongoing thinking, or what NuSelf is still considering.

Reason read tools return JSON strings for agent use. Read the fields directly;
do not treat them as a human terminal rendering.

Use {tool:context} when you need one thread's global setup and current state:
topic, description, mandates, active_items, pending_items, next_steps,
reasoning_prompt, evidence_refs, and step count.

Use {tool:step} when you need a concrete reasoning step by 0-based step index,
step id, or `latest`.

Use {tool:show} when the user asks about a specific reasoning thread and you
need both its current state and step bodies in one response.

Reason read tools omit tool logs. Tool logs are for CLI/watch/debug audit
surfaces, not ordinary agent context.

Use {tool:count} when the user only asks how many active or paused reasoning threads exist.

You may suggest creating or advancing a reasoning thread, but proposal creation policy lives in the `reason_proposal` skill. Do not call write tools from this skill.

Do not claim there are no active reasoning threads unless you have called {tool:list_active} or the answer is fully present in visible context.
