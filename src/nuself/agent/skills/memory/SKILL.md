---
name: memory
description: Use this skill when the user asks about past preferences, decisions, recurring patterns, previous discussions, stored memories, or what NuSelf remembers.
---

# Memory Skill

Durable memory is not ambient context.

CRITICAL: When the user asks about preferences, past discussions, beliefs, stored memories, or personal history, you MUST call {tool:search} before answering. Do not answer from your training data; use the tool to get the actual stored memory.

Use {tool:search} before answering unless the answer is fully present in the current visible conversation or already provided in `Relevant memory context`.

Do not say you lack memory tools when {tool:search} is listed.

If you do not call {tool:search}, do not claim that no memory exists.

You can help curate memory. If the user says something is outdated, no longer relevant, hidden, more important, or less important, confirm the intended change before using {tool:archive} or {tool:update_importance}.
