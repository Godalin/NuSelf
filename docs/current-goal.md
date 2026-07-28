# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Remove the orphaned LangMem adapter and its parallel first-endpoint model
runtime so memory generation has no hidden provider/failover protocol.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Verify the adapter has no production caller.
2. Remove the adapter, its tests, and the dead experimental config flag.
3. Remove the unused direct LangMem dependency.
4. Remove `LLMSettings.from_project`, which exists only for this bypass.
5. Regenerate the lock and verify no LangMem/runtime references remain.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Keep the active NuSelf memory curator and optimizer on shared structured
  agents.
- Keep `experimental.vector_index`; it is unrelated to this dead adapter.

## Completion Evidence

- Full-tree import search confirms the LangMem adapter had no production
  caller.
- The adapter module, its dedicated tests, `experimental.langmem_adapter`, and
  `LLMSettings.from_project` were removed.
- `pyproject.toml` and `uv.lock` contain no LangMem reference.
- Lock regeneration also removed the adapter-only `langchain`, `trustcall`, and
  `dydantic` dependency chain.
- Active memory curator and optimizer continue to use shared structured agents.
- `.venv/bin/pytest -q`: `1463 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `debcefc`.

## Next Review Batch

Remove redundant endpoint-availability preflight from reason prompt generation
and let the shared structured agent own model availability.
