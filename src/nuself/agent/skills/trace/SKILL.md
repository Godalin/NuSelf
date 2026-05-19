---
name: trace
description: Use this skill when the user asks where an idea came from, how a memory, belief, or answer formed, or what prior records support a conclusion.
allowed-tools:
  - search_trace
  - show_trace
---

# Trace Skill

Trace is NuSelf's thought provenance database.

Use `search_trace` before answering when the user asks where an idea came from, how a belief, memory, answer, reflection, or reasoning step formed, or what prior records support a conclusion.

Use `show_trace` when the user asks about a specific trace record.

Trace records summarize inspectable provenance. They are not raw hidden chain-of-thought.

Do not claim there is no provenance unless you have searched trace or the provenance is fully visible in the current conversation.
