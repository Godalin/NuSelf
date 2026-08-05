# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — repairing resumable daemon Chat approval.

## Objective

Make daemon-backed Chat pause at the exact LangGraph Tool call, present the
approval on the REPL owner thread without a timeout, and resume that checkpoint
with the user's exact decision without another model generation.

## Next Steps

1. Correct the approval-resume specification from whole-turn replay to native
   graph checkpoint continuation.
2. Preserve the original Tool call across the daemon challenge and decision.
3. Move terminal approval input out of the background activity worker.
4. Add integrated regression coverage for approve, decline, no timeout, and no
   duplicate model/Tool execution.
5. Run the full verification gates, commit in stages, and return to Idle.

## Exclusions

- Do not weaken exact request matching.
- Do not impose an approval deadline.
- Do not let daemon workers read terminal input.
- Do not rerun the model to reconstruct an interrupted Tool call.

## Completion Evidence

- The first daemon request returns one typed challenge without retrying the LLM.
- REPL presents that challenge on its input-owning thread and waits indefinitely.
- Approval resumes the exact checkpointed Tool call; decline resumes with a
  rejection Tool result; neither path regenerates Tool arguments.
- One turn and at most one approved mutation are committed.
- Full pytest, Pyright, and `git diff --check` pass.

## Progress

- Replaced whole-model replay with LangGraph `interrupt()` plus an in-memory
  per-turn checkpoint resumed through `Command(resume=...)`.
- Moved the approval prompt to the REPL owner thread with no deadline and kept
  the exact grant across transport retries.
- Added approve/decline, unchanged Tool arguments, single mutation, uncommitted
  pause, owner-thread prompt, and retry-reuse regression coverage.
- Related 355-test suite and Pyright pass; full-suite verification remains.
