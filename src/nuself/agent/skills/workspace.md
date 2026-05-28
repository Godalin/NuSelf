---
name: workspace
description: Use this skill to manage persistent key-value data in the thread's private workspace during long-run reasoning.
allowed-tools:
  - workspace_put
  - workspace_get
  - workspace_search
  - workspace_delete
---

# Workspace Skill

Each reasoning thread has an isolated private SQLite workspace. The workspace persists across advances within the same thread.

Use {tool:put} to store intermediate reasoning results, partial conclusions, branch state, counters, or other data you want to carry forward. The value must be a valid JSON string; prefer a JSON object with stable keys.

Use {tool:get} to retrieve previously stored data by key. Returns the stored JSON value or an error if the key is not found.

Use {tool:search} to find workspace entries by content query or metadata filter.

Use {tool:delete} to remove an entry only when it is no longer needed for future advances.

This workspace is thread-scoped and private. Data stored here is NOT visible to other threads, the chat agent, or the reflection subsystem. Only the reasoning process of this thread can access it.

When advancing a reason thread, use the workspace to maintain durable operational state that would be too large or too mechanical for `active_items`, such as round counters, inventories, turn order, or branch checkpoints. Read existing workspace state before creating a replacement state key.

Common use cases:
- Track which branches of reasoning you have already explored
- Store partial tracked items that are not yet ready for the thread's active_items
- Save external tool results for reuse across multiple reasoning steps
- Record meta-observations about your own reasoning process
