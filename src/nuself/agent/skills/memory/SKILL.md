---
name: memory
description: Use this skill when the user asks about past preferences, decisions, recurring patterns, previous discussions, stored memories, or what NuSelf remembers.
---

# Memory Skill

Durable memory is not ambient context.

CRITICAL: When the user asks about preferences, past discussions, beliefs, stored memories, or personal history, you MUST call `search_memory` before answering. Do not answer from your training data; use the tool to get the actual stored memory.

Use `search_memory` before answering unless the answer is fully present in the current visible conversation or already provided in `Relevant memory context`.

Do not say you lack memory tools when `search_memory` is listed.

If you do not call `search_memory`, do not claim that no memory exists.

You can help curate memory. If the user says something is outdated, no longer relevant, hidden, more important, or less important, confirm the intended change before using `archive_memory` or `update_memory_importance`.
