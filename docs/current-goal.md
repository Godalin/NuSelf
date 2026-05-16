# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in [`docs/TODOs.md`](TODOs.md), not here.

## Focus

Build v0.2.0 around three stabilizing pillars:

1. **Clean command model**: reorganize CLI and REPL commands around user-facing concepts, with no old-command compatibility aliases.
2. **Trace**: add a thought provenance database for tracing how important thoughts, answers, memories, reflections, and reason steps were derived.
3. **Reason**: add durable long-run reasoning threads for explicit user-approved questions, with trace records for creation and advances.

The release design is in [`docs/v0.2.0-design.md`](v0.2.0-design.md). Trace design is in [`docs/trace-design.md`](trace-design.md). Reason design is in [`docs/long-reasoning-design.md`](long-reasoning-design.md).

## Immediate Context

- v0.1.0 is tagged and pushed.
- The old LLM-driven decision and presentation-agent work is complete.
- The next release is intentionally breaking for command cleanup.
- `trace` is the chosen user-facing name for thought provenance.
- `reason` should integrate with `trace`: reason owns durable state; trace owns provenance.

## Next Steps

### P0 — Specs Before Code

- [ ] Update [`docs/spec/cli-interaction.md`](spec/cli-interaction.md) with the new command tree and breaking-removal policy.
- [ ] Finalize [`docs/spec/trace.md`](spec/trace.md) enough for first implementation.
- [ ] Finalize [`docs/spec/long-reasoning.md`](spec/long-reasoning.md) enough for first implementation.
- [ ] Update [`docs/spec/chat-agent-tools.md`](spec/chat-agent-tools.md) for read-only reason awareness and future trace tools.

### P1 — Command Cleanup

- [ ] Restructure parser construction around `daemon`, `thread`, `memory`, `inbox`, `reason`, `trace`, and `dev`.
- [ ] Move `source` under `memory source`.
- [ ] Move `reflection` and `notify` under `inbox`.
- [ ] Move `logs`, `status`, `health`, `config`, and `eval` under `dev`.
- [ ] Rename `memory candidate` to `memory review`.
- [ ] Rename `thread create` to `thread new`.
- [ ] Update REPL command groups to match.

### P2 — Trace Foundation

- [ ] Add `ThoughtTrace`, `TraceLink`, `TraceRepository`, and renderers.
- [ ] Add `nuself trace list/show/search`.
- [ ] Add `:trace` commands.

### P3 — Reason Foundation

- [ ] Add `ReasoningThread`, `ReasoningStep`, and repositories.
- [ ] Add `nuself reason list/show/start/advance/pause/resume/resolve/archive`.
- [ ] Add `:reason` commands.
- [ ] Make reason thread creation and advance write trace records.
- [ ] Add reflection promotion into reason and trace.

## Not Now

- Old command compatibility aliases.
- Scheduled reason advancement.
- Reason notifications.
- Trace graph visualization.
- Raw hidden model chain-of-thought capture.
- Vector or graph search for trace.

## Completion Criteria

- New command tree is implemented and documented.
- Old command paths are removed.
- Trace records can be listed, shown, and searched.
- Reason threads can be created, shown, advanced, paused, resumed, resolved, and archived.
- Reflection promotion creates a reason thread and trace record.
- Chat can read active reason summaries without silently creating reason threads.
- README, specs, TODOs, and CHANGELOG are synchronized.
- `uv run pytest`, `uvx pyright`, and `git diff --check` pass.
