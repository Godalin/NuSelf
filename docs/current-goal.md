# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in [`docs/TODOs.md`](docs/TODOs.md), not here.

## Focus

Decouple reflection from the notification outbox. Reflection ideas become first-class domain objects in their own repository (`private/reflections/`). The notification outbox becomes a generic event bus that can be used by any background job (reflection with `auto_notify`, memory curator, etc.).

## Immediate Context

The reflection/notify decoupling is complete:

- **ReflectionRepository** (`private/reflections/`): Stores reflection entries with `pending` / `dismissed` / `archived` status.
- **ReflectionScheduler** no longer writes directly to `NotificationOutbox`. It writes to `ReflectionRepository` by default.
- **`auto_notify` config**: When `true`, a brief outbox entry is created pointing to the reflection.
- **CLI refactored**: `reflection list/show/dismiss/archive` all operate on `ReflectionRepository`, supporting `--by-index`.
- **Chat agent tools updated**: `list_pending_reflections` and `dismiss_reflection` now read from `ReflectionRepository` instead of `NotificationOutbox`.
- **Specs updated**: `docs/spec/reflection.md`, `docs/spec/notification.md`, `docs/spec/chat-agent-tools.md` rewritten to match new architecture.
- **READMEs synchronized**: Both English and Chinese versions document the new reflection and notify behavior.
- **JSON Schema**: `docs/nuself-config.schema.json` added for VS Code YAML validation.
- **pyright clean**: 0 errors after fixing all type issues introduced by the refactor.
- **Tests**: 585 passed. New `test_reflection_repository.py` covers CRUD, status filtering, dismiss/archive.

## Next Steps

1. **Stabilize**: Run extended manual REPL verification to confirm tool invocation and memory curation work smoothly.
2. **Decide next milestone**: Options include memory optimizer integration, vector/hybrid indexes, or hot reload of reflection config.

### Recently Done

- Decoupled reflection from notification outbox.
- Created `ReflectionRepository` with `ReflectionEntry` (pending/dismissed/archived).
- Updated `ReflectionScheduler` to store ideas in `ReflectionRepository`.
- Added `auto_notify` to `ReflectionSettings`.
- Refactored CLI reflection commands to use `ReflectionRepository`.
- Updated chat agent tools (`list_pending_reflections`, `dismiss_reflection`) to use `ReflectionRepository`.
- Updated all specs to match new architecture.
- Updated README.md and README.zh-CN.md.
- Added JSON Schema for config.yaml.
- Fixed all pyright type errors.

## Not Now

- LLM-less reflection (Phase 3).
- Hot reload of reflection config.
- Vector and hybrid indexes.
- Automatic reflection-to-memory conversion without user chat engagement.

## Completion Criteria

- Reflection ideas live in `private/reflections/`, not mixed into notify outbox.
- `nuself reflection list/show/dismiss/archive` work correctly.
- Chat agent tools read from `ReflectionRepository`.
- `auto_notify` optionally creates brief outbox entries.
- All specs and READMEs synchronized.
- All tests pass, pyright clean.
