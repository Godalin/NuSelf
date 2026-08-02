---
name: source
description: Use this skill when the user asks about imported documents, notes, references, research material, or external library content.
allowed-tools:
  - source_search
  - source_get
  - source_list
---

# Source Skill

External Source material is not personal memory and is not ambient context.

Use {tool:search} when the question may benefit from imported documents or library material. Search with a short topic query. If the first result is empty and relevant material may exist, call {tool:search} exactly once more with a distinct broader query. Do not repeat searches indefinitely.

Use {tool:get} after search when a selected document or chunk needs fuller content. Use {tool:list} only when the user asks what material is available or needs help selecting a source.

Treat Source results as external evidence. Never describe a document statement as the user's belief, preference, experience, or memory unless the visible conversation independently establishes that relationship.
