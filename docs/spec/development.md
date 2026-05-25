# Development Process Spec

## Code Standard

- Standard Python project managed by `uv`.
- Type-check with `uvx pyright`.
- Sub-components must be individually tested.
- User-facing changes must update both `README.md` and `README.zh-CN.md`.
- Track progress in [`docs/TODOs.md`](docs/TODOs.md); short-term focus in `docs/current-goal.md`.

## Commit And Push Policy

- Separate commits:
  1. **Functional commit**: code + tests.
  2. **Progress commit**: `docs/current-goal.md`, README TODOs, and spec updates.
- Before non-trivial work, check `docs/current-goal.md`. Mention conflicts before proceeding.
- Push normal development commits only when the user asks to publish or sync the branch.
- Before pushing, confirm the working tree is clean and the intended commits are on the current branch.
- Normal branch push command: `git push`.
- If a release tag was created, push the release commit and tag together: `git push && git push origin v<version>`.

## Release And Tag Policy

Versioning and changelog rules live in [`versioning.md`](versioning.md). Release work must follow that spec plus this concrete flow:

1. Finish and verify all intended functional commits.
2. Move relevant `CHANGELOG.md` `Unreleased` entries into a dated version section and create a fresh empty `Unreleased` section.
3. Bump `pyproject.toml` to the release version. Runtime `nuself.__version__` must continue to resolve to the package metadata version.
4. Run `uv run pytest`, `uvx pyright`, and `git diff --check`.
5. Confirm `uv run nuself --version` prints the intended version.
6. Commit the release metadata with message `release: <version>`.
7. Create an annotated git tag: `git tag -a v<version> -m "Release <version>"`.
8. Push the release commit and tag together when the user asks to publish: `git push && git push origin v<version>`.

Do not tag unreleased feature commits directly. Tags mark release commits only.

## Development Style

- **Design before implement**: For any non-trivial feature or behavioral change, write or update the relevant spec document **before** writing implementation code.
- **Spec is authoritative**: A feature change is not complete until the spec that governs it is updated in the same change.
- **No spec drift**: If code behavior diverges from its spec, either fix the code or update the spec. The spec must always describe the actual system.
- Early development: prefer direct, clean implementation over compatibility shims.
- Interface changes must update all callers, tests, examples, and docs in the same commit.
- Configuration shape changes must update `docs/spec/config.md`, `docs/nuself-config.schema.json`, `examples/private/config.yaml`, and relevant config tests in the same change.
- Do not preserve obsolete CLI commands, protocols, schemas, or APIs unless a document explicitly requires them.
- Refactors are welcome when they clarify architecture; always pair them with doc and test updates.
- Keep `docs/current-goal.md` concise (active focus, next steps, out-of-scope, completion criteria). Move completed history to README TODOs.
- Keep scoped implementation constraints in local `AGENTS.md` files near the code, not the root README.

## Framework-Native Agent Architecture

NuSelf uses LangChain/LangGraph as the agent infrastructure layer. When the framework has a current recommended API for an agent concern, NuSelf must use that API rather than maintain an equivalent private protocol.

Rules:

- Tool calling must use LangChain tool objects and model/agent tool-calling APIs such as `bind_tools(...)` or `create_agent(..., tools=[...])`. Models must not be asked to print ad-hoc visible markers or NuSelf-only tool-call text.
- Structured agent output should use LangChain structured-output mechanisms where practical, such as `create_agent(..., response_format=...)` or provider/tool strategies. Prompted JSON may remain only as a bounded fallback for non-agent subsystems until they are migrated.
- Stateful agent workflows should use LangGraph state graphs or LangChain agents/middleware. NuSelf may own domain state and persistence, but should not duplicate framework runtime concepts.
- Agent skills, middleware, model invocation, retries, tool execution, and message passing should follow current LangChain documentation. Any deliberate deviation must be documented in the relevant spec with a reason and a migration path.
- Custom code should focus on NuSelf domain semantics: memory, reflection, reason, trace, private storage, rendering, and logs.

## Subsystem Service Architecture

NuSelf is a multi-subservice system. Major domains such as memory, reflection, notification, trace, and reason should be implemented as clear subsystems rather than as incidental CLI helpers.

Each subsystem should expose these layers when the domain is non-trivial:

1. **Domain models**: typed records and validation rules.
2. **Repository**: file-backed persistence and rebuildable indexes.
3. **Service**: user-intent operations and policy decisions.
4. **Renderer**: human-readable CLI/REPL presentation.
5. **Tool-facing adapter**: a small interface suitable for use by chat, reason, reflection, or future agents.
6. **Agent skill**: prompt-level policy that tells agents when and why to use the subsystem's tools.

Rules:

- Agents should call service/tool-facing interfaces, not read or write subsystem storage files directly.
- CLI and REPL commands should be thin wrappers over service methods when behavior is non-trivial.
- Cross-subsystem effects should be explicit. For example, reason may call trace recording through `TraceRecorder`, not by constructing private trace files itself.
- Tool-facing interfaces must use small typed inputs and outputs, avoid leaking raw file paths unless intentionally requested, and be safe to expose to LLM-driven agents.
- Tool-facing interfaces define capability; agent skills define usage policy. A service exposed to agents should usually provide both.
- Agent skills must be explicit about when tool use is expected, when it is optional, and what claims are invalid without a tool result.
- Shared renderers should be reused so CLI, REPL, transcripts, and logs stay consistent.

## Memory Architecture Direction

- Prefer open typed memory (`MemoryObject + MemoryTypeDescriptor`) over closed enums.
- Descriptors own validation, summarization, merge, decay, conflict, retrieval, and reflection rules.
- Symbolic memory evolves as a derived open graph with `RelationDescriptor` rules.
- File-backed private memory is authoritative; all indexes are derived and rebuildable.

## Private Memory

- Real personal memory lives in the root `private/` directory.
- `private/` is ignored by Git and must not be committed.
- Code loads from `private/` by default; tests and demos use `examples/private/`.
