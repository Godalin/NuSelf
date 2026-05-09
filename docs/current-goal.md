# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Importance and unknown-type quarantine are wired across the memory pipeline.

## Immediate Context

- `MemoryEntry`, `MemoryObject`, `MemoryCandidate`, and `ProfileItem` all carry `importance: float` with full serialization.
- `MemoryTypeDescriptor.importance()` and `MemoryTypeRegistry.importance()` delegate with per-type defaults.
- `EntryPayloadDescriptor.default_importance` gives profile_fact 0.9, open_question 0.3, etc.
- `MemoryQueryService` scores by importance and supports `min_importance` filter.
- `MemorySearchFilters` supports `min_importance` for repository-level filtering.
- CLI `memory add/edit` and `memory candidate edit` accept `--importance`; `memory search` accepts `--min-importance`; `memory list`, `memory profile list`, and `memory candidate list` accept `--sort-by`; `memory list` and `memory candidate list` accept `--review-state`.
- `MemoryIntakeAgent` infers importance from user text, with per-type default importance for local fallback.
- `memory stats` reports `avg_importance` and `max_importance`.
- `memory show/list` and candidate summary/detail render importance in output.
- `ReviewState` now includes `quarantined`; unknown-type draft entries are auto-quarantined on save.
- `MemoryEntryRepository.unquarantine()` restores quarantined entries to draft.
- CLI `memory unquarantine <id>` allows manual recovery of quarantined entries.
- `memory search --review-state quarantined` can list quarantined entries.

## Next Steps

1. ~~Add `importance` field to `MemoryEntry`, `MemoryObject`, and `MemoryCandidate`.~~ Done.
2. ~~Add `importance` hook to `MemoryTypeDescriptor` and `MemoryTypeRegistry`.~~ Done.
3. ~~Wire importance into `MemoryQueryService` scoring.~~ Done.
4. ~~Add `--importance` to CLI `memory add`, `memory edit`, and `memory candidate edit`.~~ Done.
5. ~~Add round-trip and scoring tests for importance.~~ Done.
6. ~~Add per-type default importance values via `EntryPayloadDescriptor.default_importance`.~~ Done.
7. ~~Add `--min-importance` to `memory search`.~~ Done.
8. ~~Add importance stats to `memory stats`.~~ Done.
9. ~~Surface importance in `memory show/list` and candidate output.~~ Done.
10. ~~Add unknown-type quarantine with auto-quarantine on save.~~ Done.
11. ~~Add `memory unquarantine` CLI command.~~ Done.
12. ~~Update `README.md` and `README.zh-CN.md` TODOs for importance and quarantine.~~ Done.

## Not Now

- Full multi-persona orchestration beyond the current bounded skeleton.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- `MemoryEntry`, `MemoryObject`, `MemoryCandidate`, and `ProfileItem` serialize and deserialize `importance`.
- `MemoryTypeDescriptor` exposes `importance(memory) -> float` with per-type defaults.
- `MemoryQueryService` scores by importance and supports `min_importance` filtering.
- `MemorySearchFilters` and `MemoryStats` include importance fields.
- CLI `memory add/edit` and `memory candidate edit` accept `--importance`; `memory search` accepts `--min-importance`.
- `memory stats` reports `avg_importance`, `max_importance`, and `avg_importance_by_type`.
- `memory show/list` and candidate output render importance.
- Unknown-type draft entries are auto-quarantined on save; non-draft unknown types raise.
- `MemoryEntryRepository.unquarantine()` restores quarantined entries to draft.
- CLI `memory unquarantine` command works and `memory search --review-state quarantined` lists quarantined entries.
- Tests cover round-trip, registry delegation, scoring, filtering, stats, candidate behavior, and quarantine.
- All operations are type-checked and tested.
