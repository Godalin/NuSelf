# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Real-time outbox watch mode for observing daemon proactive reflection output as it arrives.

## Immediate Context

- `notify watch` CLI command polls the outbox every 5s (configurable via `--interval`) and prints new entries as they appear.
- REPL `:watch` command enters the same watch mode with 2s polling.
- Both modes track already-seen entries and only emit new ones, using the existing color-coded `render_outbox_summary`.
- 522 tests pass, pyright clean.

## Next Steps

1. ~~Add `notify watch` CLI command with `--interval` flag.~~ Done.
2. ~~Add REPL `:watch` command.~~ Done.
3. ~~Update README and README.zh-CN.md TODOs.~~ Done.
4. Commit feature code and docs separately.

## Not Now

- Full multi-persona orchestration beyond the current bounded skeleton.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.
- Background log polling in normal REPL input mode (watch mode is explicit).

## Completion Criteria

- `nuself notify watch` prints new outbox entries in real time.
- REPL `:watch` enters watch mode and exits cleanly on Ctrl+C.
- All new code passes `uv run pytest` and `uvx pyright`.
- `README.md` and `README.zh-CN.md` TODOs updated.
