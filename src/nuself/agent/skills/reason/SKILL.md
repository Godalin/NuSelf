---
name: reason
description: Use this skill when the user asks about active long-running thinking, open reasoning threads, or what NuSelf is continuing to think about.
---

# Reason Skill

Reason is NuSelf's durable long-run thinking space. Each thread tracks
progress through general-purpose state: active_items (what you're tracking),
pending_items (what's unresolved), and next_steps (planned actions).
Items carry free-text kind labels — choose whatever fits the task
(hypothesis, character, suspect, plot_thread, world_rule, ...).

Use {tool:list_active} before answering when the user asks about active long-running thinking, open threads, ongoing thinking, or what NuSelf is still considering.

Use {tool:show} when the user asks about a specific reasoning thread.

Use {tool:propose} after the user has discussed a topic in depth and explicitly confirmed they want a thinking thread. Pass the enriched context: the final topic, a working_summary of key insights, initial tracked items as active_items (each with "label", optional "description", and a free-text "kind" tag), any required mandates the thread should enforce, and evidence_refs. The proposal will be confirmed once more before creation.

Before proposing, discuss with the user whether the thread needs any **mandates** — required actions the advancer must follow on every advance. For example, "use persona_craft to create at least one new persona before each advance" ensures diverse perspectives. Mandates are architectural constraints, not suggestions.

Consider using persona_list and persona_think to gather different perspectives on the topic. In a reasoning thread you can also create local personas via persona_craft that are private to that thread — this is useful when a specific angle or expertise is needed for the thread's topic.

You may suggest creating or advancing a reasoning thread, but must not create, advance, resolve, or archive one without explicit user confirmation.

Do not claim there are no active reasoning threads unless you have called {tool:list_active} or the answer is fully present in visible context.
