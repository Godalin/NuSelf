# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make service ownership intrinsic to every chat tool definition and remove
construction-time name mapping and metadata mutation.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit every chat tool construction site.
2. Specify definition-time service ownership.
3. Add service metadata to each tool definition.
4. Delete the name-to-service table and post-construction mutation.
5. Verify the complete registry has expected ownership.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Do not change tool names, descriptions, schemas, tags, or execution behavior.
- Keep persona and workspace builders independently composable.
- Do not introduce a replacement central catalog.

## Completion Evidence

- Every tool built directly by `build_langchain_chat_tools` declares
  `service_component` in its own constructor call.
- The name-to-service table and post-construction `tool.metadata` mutation are
  deleted; production and test search finds neither pattern.
- The runtime registry test verifies service ownership for every chat,
  persona, selves, and skill-loader tool.
- Tool names, descriptions, schemas, tags, and execution paths are unchanged.
- `.venv/bin/pytest -q`: `1471 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `991edbc`.

## Next Review Batch

Review the monolithic chat tool builder and define subsystem-owned registration
boundaries.
