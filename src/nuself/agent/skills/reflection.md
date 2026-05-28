---
name: reflection
description: Use this skill when the user asks for ideas, thoughts, reflections, or open-ended exploration that may benefit from pending proactive reflection ideas.
allowed-tools:
  - reflection_list_pending
  - reflection_count
  - reflection_dismiss
  - reflection_archive
---

# Reflection Skill

Reflection ideas are proactive suggestions, not facts about the user.

CRITICAL: When the user asks about pending reflections, ideas, thoughts, or open-ended exploration, you MUST call {tool:list_pending} before answering. Do not list reflections from your training data; always use the tool.

If the user explicitly asks to query, check, list, or inspect pending reflection ideas, call {tool:list_pending} before answering.

Use {tool:list_pending} when the user asks for ideas, thoughts, or reflections, when the conversation naturally pauses, or when the topic strongly matches proactive exploration.

Use {tool:count} when the user asks how many pending reflection ideas exist.

Introduce at most one reflection idea in natural language unless the user explicitly asks for a list.

Do not dump the raw reflection list into the answer.

Use {tool:dismiss} only when the user explicitly declines a topic.

Use {tool:archive} only after the user has engaged with a reflection and the discussion feels complete. If the user's intent is ambiguous, ask before mutating reflection state.
