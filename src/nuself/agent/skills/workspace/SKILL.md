---
name: workspace
description: Use this skill to manage persistent key-value data in the thread's private workspace during long-run reasoning.
---

# Workspace Skill

Each reasoning thread has an isolated private SQLite workspace. The workspace persists across advances within the same thread.

Use {tool:put} to store intermediate reasoning results, partial conclusions, branch state, or any data you want to carry forward. The value must be a JSON object.

Use {tool:get} to retrieve previously stored data by key. Returns a JSON object or an error if the key is not found.

Use {tool:search} to find workspace entries by content query or metadata filter.

Use {tool:delete} to remove an entry when it is no longer needed.

This workspace is thread-scoped and private. Data stored here is NOT visible to other threads, the chat agent, or the reflection subsystem. Only the reasoning process of this thread can access it.

Common use cases:
- Track which branches of reasoning you have already explored
- Store partial hypotheses that are not yet ready for the thread's `new_hypotheses` field
- Save external tool results for reuse across multiple reasoning steps
- Record meta-observations about your own reasoning process
