---
name: trace
description: Use this skill when the user asks where an idea came from, how a memory, belief, or answer formed, or what prior records support a conclusion.
allowed-tools:
  - trace_search
  - trace_count
  - trace_show
  - trace_related
---

# Trace Skill

Trace is NuSelf's thought provenance database.

Use {tool:search} before answering when the user asks where an idea came from, how a belief, memory, answer, reflection, or reasoning step formed, or what prior records support a conclusion.

Use {tool:count} when the user asks how many trace records match a topic or query.

Use {tool:show} when the user asks about a specific trace record.

Use {tool:related} when the user asks what trace records mention a specific artifact reference such as `memory:<id>`, `reflection:<id>`, `reason:<id>`, or `reason_step:<id>`.

Trace records summarize inspectable provenance. They are not raw hidden chain-of-thought.

Do not claim there is no provenance unless you have searched trace or the provenance is fully visible in the current conversation. If trace search is empty, say no matching trace was found rather than making a broader claim.
