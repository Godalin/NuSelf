# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Store persona instructions and corrections as procedural memory.

The bounded persona skeleton now runs behind an activation gate and feeds synthesis into the response prompt. Persona definitions (`analyst_self`, `skeptic_self`, `builder_self`, `historian_self`, `care_self`, and `synthesizer_self`) are currently hard-coded in `nuself.agent.persona`. The next step is to let these definitions live as durable memory entries under the existing `MemoryEntry` system, so they can be inspected, edited, and versioned like any other memory object, while still being loaded efficiently at runtime.

## Immediate Context

- `PersonaDefinition` is a small dataclass with `id` and `description`.
- `PersonaActivationPolicy` uses hard-coded markers and persona references.
- `MinimalPersonaNode` and `MinimalSynthesizerNode` use hard-coded logic per persona.
- `MemoryEntryRepository` already supports open typed memory via `MemoryObject + MemoryTypeDescriptor`.
- The `instruction` memory type descriptor exists and can store structured procedural knowledge.
- `PersonaGraphDriver` compiles a LangGraph graph at init time using the current persona nodes.

## Next Steps

1. Design a `MemoryObject` payload schema for persona instructions (id, description, routing markers, and optional behavioral notes).
2. Register a `PersonaInstructionDescriptor` that validates the payload and exposes a compact summary.
3. On `PersonaGraphDriver` or `PersonaActivationPolicy` initialization, load persona definitions from memory entries of type `instruction` with a `persona` tag, falling back to hard-coded defaults when no durable definitions exist.
4. Let the REPL or CLI print a compact indicator when durable persona instructions are being used instead of defaults.
5. Ensure loading is lazy and cached so chat latency is not affected.
6. Add tests proving that custom persona instructions override defaults and that invalid entries are rejected by the descriptor.

## Not Now

- Full multi-persona orchestration.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- Persona definitions can be stored as durable `instruction` memory entries.
- Runtime loads persona definitions from memory when available, falling back to hard-coded defaults.
- Invalid persona instruction payloads are rejected by the descriptor.
- Default chat behavior is unchanged when no custom persona instructions exist.
- All operations are type-checked and tested.
- README TODOs track completed progress, while this file stays limited to the active goal.
