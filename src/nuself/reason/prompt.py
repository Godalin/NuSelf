"""Reasoning prompt generation — produces topic-specific system prompts."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import StructuredTool

from nuself.llm import ChatMessage, configured_langchain_chat_models, default_llm
from nuself.reason.errors import ReasonPromptError


def generate_reasoning_prompt(
    topic: str,
    *,
    mandates: tuple[str, ...] = (),
    active_items: tuple[dict[str, object], ...] = (),
    project_root: Path | None = None,
) -> str:
    """Generate a custom reasoning system prompt for a thread topic."""
    if project_root is None:
        raise ReasonPromptError(
            "Cannot generate reasoning prompt: project root is not configured"
        )
    if not configured_langchain_chat_models(project_root):
        raise ReasonPromptError(
            "Cannot generate reasoning prompt: no LangChain chat model is configured"
        )
    parts = [
        "You are setting up a reasoning thread. The user's topic is:",
        topic,
    ]
    if mandates:
        parts.append("\nConstraints that apply:")
        for m in mandates:
            parts.append(f"  - {m}")
    if active_items:
        parts.append("\nInitial items being tracked:")
        for item in active_items:
            label = item.get("label", "")
            kind = item.get("kind", "")
            desc = item.get("description", "")
            desc_text = f" — {desc}" if desc else ""
            parts.append(f"  - {label} ({kind}){desc_text}")
    parts.append(
        """
Generate a concise system prompt (2-4 paragraphs) for a reasoning agent
that will advance this thread one step at a time. The agent sees this
prompt before EVERY step, so it should set the tone and explain the
fields in terms of THIS specific topic.

The prompt must cover:

1. What kind of thinking this is (e.g. story writing, scientific analysis,
   debate, investigation, design). Set the appropriate voice and pace.

2. Explain what each field means IN THE CONTEXT OF THIS TOPIC:
   - output — the visible product of each step. What form does it take
     for this topic? (e.g. story paragraph, analysis paragraph, design
     sketch, argument)
   - active_items — what kind of things will be tracked here?
     (e.g. characters and plot threads for a story; hypotheses and
     evidence for science; arguments for debate)
   - pending_items — what kind of open questions?
   - new_findings — what counts as a new insight?
   - delta — what kind of change matters?
   - retired_findings — when does something get set aside?

3. The pace: how much should one step accomplish? Focused or broad?
   Define the smallest bounded advance unit for this topic. For simulations,
   debates, interviews, games, or staged discussions, one step must mean at
   most one complete round. If setup is needed, setup may happen before the
   first round, but the same step must not skip ahead through multiple rounds.

4. Persona tool grounding, when relevant: if the topic uses explicit personas
   as participants, reviewers, interviewees, or staged speakers, state that
   persona_craft may create local personas, but every later persona utterance,
   answer, critique, vote, judgment, or dialogue line must be produced by
   calling persona_think for that persona in the same step. The reasoning agent
   must not simulate local persona speech directly in output.

5. Terminal recommendation: define when the reasoning agent should use
   terminal_status=continue, suggest_resolved, or suggest_paused for this
   specific topic. For debates, simulations, interviews, games, or staged
   discussions, map explicit completion, collapse, victory, failure, or
   waiting-for-user conditions to the appropriate terminal status.

6. Any special rules derived from the constraints.

Write in second person ("You are..."). Keep it concise but specific.
Do NOT include field type/format descriptions — only explain meaning.
"""
    )
    prompt = "\n".join(parts)
    try:
        llm = default_llm(project_root)
        raw = llm.complete([ChatMessage(role="user", content=prompt)])
    except RuntimeError as exc:
        raise ReasonPromptError(
            f"Cannot generate reasoning prompt: {exc}"
        ) from exc
    rendered = raw.strip()
    if not rendered:
        raise ReasonPromptError(
            "Cannot generate reasoning prompt: model returned an empty prompt"
        )
    return rendered


def build_reasoning_prompt_tools(project_root: Path | None) -> tuple[StructuredTool, ...]:
    """Build tools for generating custom reasoning prompts."""

    def _run(topic: str, context: str = "") -> str:
        """Generate a custom reasoning system prompt for a given topic.

        The returned prompt sets the tone and explains the reasoning fields
        in terms of the specific topic, so the reasoning agent produces
        relevant output for each step.
        """
        return generate_reasoning_prompt(topic, project_root=project_root)

    return (
        StructuredTool.from_function(  # pyright: ignore[reportUnknownMemberType]
            func=_run,
            name="reasoning_prompt_gen",
            description="Generate a custom reasoning system prompt for a topic. The prompt explains what output, active_items, pending_items, new_findings, and delta mean in the context of this specific topic.",
        ),
    )
