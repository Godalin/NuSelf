# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Enhanced outbox/notify terminal interface with color-coded formatting, filtering, and richer REPL commands.

## Immediate Context

- `notify list` now supports `--status` filtering and color-coded output via `TerminalTheme`.
- `notify show` renders formatted detail with colored status tags.
- `notify stats` prints counts by status.
- REPL `:notify list` shows all entries; `:notify show <id>` shows detail.
- All outbox rendering lives in `tui/render.py` alongside log/event renderers.
- 519 tests pass, pyright clean.

## Next Steps

1. ~~Add color-coded outbox formatting in `tui/render.py`.~~ Done.
2. ~~Add `--status` filter to `notify list` and enhance output.~~ Done.
3. ~~Enhance `notify show` with formatted detail view.~~ Done.
4. ~~Add `notify stats` CLI command.~~ Done.
5. ~~Add REPL `:notify list` and `:notify show <id>`.~~ Done.
6. ~~Update README and README.zh-CN.md TODOs.~~ Done.
7. Commit feature code and docs separately.

## Not Now

- Full multi-persona orchestration beyond the current bounded skeleton.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- `notify list --status <filter>` works and outputs color-coded lines.
- `notify show <id>` outputs formatted detail with colored status.
- `notify stats` prints counts by status.
- REPL `:notify list` and `:notify show <id>` work.
- All new code passes `uv run pytest` and `uvx pyright`.
- `README.md` and `README.zh-CN.md` TODOs updated.
