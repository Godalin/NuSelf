# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in [`docs/TODOs.md`](TODOs.md), not here.

## Focus

Build v0.2.0 around three stabilizing pillars:

1. **Clean command model**: reorganize CLI and REPL commands around user-facing concepts, with no old-command compatibility aliases.
2. **LLM endpoint failover**: allow multiple configured LLM endpoints and remember the last working endpoint across runs.
3. **Trace**: add a thought provenance database for tracing how important thoughts, answers, memories, reflections, and reason steps were derived.
4. **Reason**: add durable long-run reasoning threads for explicit user-approved questions, with trace records for creation and advances.

The release design is in [`docs/v0.2.0-design.md`](v0.2.0-design.md). Trace design is in [`docs/trace-design.md`](trace-design.md). Reason design is in [`docs/long-reasoning-design.md`](long-reasoning-design.md).

## Immediate Context

- v0.1.0 is tagged and pushed.
- The old LLM-driven decision and presentation-agent work is complete.
- The next release is intentionally breaking for command cleanup.
- `trace` is the chosen user-facing name for thought provenance.
- `reason` should integrate with `trace`: reason owns durable state; trace owns provenance.
- LLM endpoint failover should use a direct `llm` endpoint list. Endpoints default to OpenAI-compatible behavior; `anthropic: true` marks Anthropic endpoints. Do not introduce a broad provider plugin layer yet.
- **Go endpoint unblocked**: `minimax-m2.5` returns 400, superseded by `minimax-m2.7`. Config updated and connectivity verified.
- **Reason subsystem implemented**: `src/nuself/reason/` with domain models, repository, service, CLI commands, REPL commands, and TUI renderers. 31 tests passing.

## Next Steps

### P0 — Specs Before Code

- [x] Update [`docs/spec/cli-interaction.md`](spec/cli-interaction.md) with the new command tree and breaking-removal policy.
- [x] Finalize [`docs/spec/trace.md`](spec/trace.md) enough for first implementation.
- [x] Finalize [`docs/spec/long-reasoning.md`](spec/long-reasoning.md) enough for first implementation.
- [x] Update [`docs/spec/chat-agent-tools.md`](spec/chat-agent-tools.md) for read-only reason awareness and future trace tools.

### P1 — Command Cleanup

- [x] Restructure parser construction around `daemon`, `thread`, `memory`, `inbox`, `reason`, `trace`, and `dev`.
- [x] Move `source` under `memory source`.
- [x] Move `reflection` and `notify` under `inbox`.
- [x] Move `logs`, `status`, `health`, `config`, and `eval` under `dev`.
- [x] Rename `memory candidate` to `memory review`.
- [x] Rename `thread create` to `thread new`.
- [x] Update REPL command groups to match.

### P2 — LLM Endpoint Failover

- [x] Add direct `llm` endpoint-list config support.
- [x] Support OpenAI-compatible endpoints by default and Anthropic endpoints via `anthropic: true`.
- [x] Add runtime state for the last successful LLM endpoint.
- [x] Fail over on subscription/quota/auth/account availability errors.
- [x] Log endpoint switches without exposing API keys.

### P3 — Trace Foundation

- [x] Add `ThoughtTrace`, `TraceLink`, `TraceRepository`, and renderers.
- [x] Add `nuself trace list/show/search`.
- [x] Add `:trace` commands.

### P4 — Reason Foundation

- [x] Add `ReasoningThread`, `ReasoningStep`, and repositories.
- [x] Add `nuself reason list/show/start/advance/pause/resume/resolve/archive`.
- [x] Add `:reason` commands.
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
