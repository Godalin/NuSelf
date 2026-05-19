---
name: reflection
description: Use this skill when the user asks for ideas, thoughts, reflections, or open-ended exploration that may benefit from pending proactive reflection ideas.
allowed-tools:
  - list_pending_reflections
  - dismiss_reflection
  - archive_reflection
---

# Reflection Skill

Reflection ideas are proactive suggestions, not facts about the user.

Use `list_pending_reflections` only when the user asks for ideas, thoughts, or reflections, when the conversation naturally pauses, or when the topic strongly matches proactive exploration.

Introduce at most one idea in natural language.

Do not dump the raw reflection list into the answer.

Use `dismiss_reflection` when the user declines a topic.

Use `archive_reflection` when the user engages and the discussion feels complete.
