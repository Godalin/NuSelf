# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in [`docs/TODOs.md`](docs/TODOs.md), not here.

## Focus

Replace hardcoded numeric scoring and heuristic rules with LLM-driven contextual decisions. This is a defining architectural characteristic of the project: the LLM is not only a generator but also the primary decision-maker for all judgments that require understanding context, nuance, and user state.

The LLM-Driven Decision manifesto (ten principles) is now in [`docs/architecture.md`](architecture.md).

## Immediate Context

The three-layer decision stack is documented in [`docs/architecture.md`](architecture.md) and behavioral contracts are in [`docs/spec/llm-driven-decisions.md`](spec/llm-driven-decisions.md):

- **L0 Infrastructure**: deterministic mechanical operations (file I/O, clamping, time arithmetic)
- **L1 Policy**: user-configurable rules (daily_cap, quiet_hours, cooldown_seconds)
- **L2 Judgment**: LLM-driven contextual decisions (relevance, novelty, persona matching, discussion depth)

Previous work (reflection decoupling, language preference, env-var removal, chat reflection tools) is complete and committed.

## Next Steps (design → spec → impl)

### Proposed: P3 — Presentation Agent Split

- [x] **Design**: Drafted [`docs/presentation-agent-design.md`](presentation-agent-design.md)
- [x] **Spec**: Drafted [`docs/spec/presentation-agent.md`](spec/presentation-agent.md)
- [ ] **Approval**: Confirm the split between thinking/tool/persona stages and final user-facing presentation
- [ ] **Impl**: Introduce internal draft response and final presentation response types
- [ ] **Test**: Verify protocol/persona leakage triggers one LLM regeneration, not string rewriting

Intent: separate "what NuSelf thinks should be said" from "how NuSelf says it beautifully and appropriately." This keeps presentation as an L2 judgment task and avoids mechanical output surgery.

### Done: P0 — LLMRelevanceGate

- [x] **Design**: Three-layer stack + ten-principle manifesto written to `docs/architecture.md`
- [x] **Spec**: P0 contract written to `docs/spec/llm-driven-decisions.md`
- [x] **Impl**: `LLMRelevanceGate` class added to `scheduler.py` (replaces deleted `RelevanceGate`)
- [x] **Test**: Rewrote `test_reflection_scheduler.py` with `FakeLLM` deterministic JSON responses
- [x] **Verify**: `pytest` + `pyright` clean

### Done: P1 — Persona Activation + Host Escalation

- [x] **Spec**: Defined `LLMBackedActivationPolicy` prompt schema and fallback behavior in `docs/spec/llm-driven-decisions.md`
- [x] **Impl**: `LLMBackedActivationPolicy` replaces both `PersonaActivationPolicy` and `HostDiscussionPolicy`
  - Single LLM call decides selected personas + escalation
  - Structured JSON output: `activated`, `selected_persona_ids`, `trigger`, `should_escalate`, `escalation_reason`
  - Safe fallback on any LLM/JSON/parsing failure
- [x] **Test**: FakeLLM tests for activation, escalation, fallback, unknown persona IDs, string bool parsing
- [x] **Verify**: `pytest` (591 passed) + `pyright` (0 errors) clean

### Done: P2 — Persona Discussion Scoring

- [x] **Spec**: Defined LLM-reported score schema, moderator judgment, emergent persona rules, and deterministic participant turns
- [x] **Impl**: Replaced heuristic scoring, consensus checks, emergent-persona heuristics, and random persona selection with LLM-backed decisions plus safe fallbacks
- [x] **Test**: Added deterministic FakeLLM fixtures for scoring, selection, moderator convergence, emergent personas, and approval/blocking outcomes

## Not Now

- Memory query scoring (`memory/query.py`) — keep lexical L0, defer LLM reranking to hybrid-search milestone
- P3+ LLM-less reflection (Phase 3)
- Vector and hybrid indexes

## Completion Criteria

- [x] P0: `LLMRelevanceGate` passes tests with FakeLLM, fallback verified, pyright clean
- [x] P1: `LLMBackedActivationPolicy` replaces keyword-marker heuristics and length thresholds with LLM judgment
- [x] P2: Persona discussion uses LLM-reported scores
- [x] All specs and architecture docs synchronized
- [x] All tests pass, pyright clean
