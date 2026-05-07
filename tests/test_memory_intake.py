from __future__ import annotations

from nuself.memory.intake import MemoryIntakeAgent


def test_memory_intake_locally_infers_goal() -> None:
    result = MemoryIntakeAgent().infer(body="My goal is to finish the memory system planning.")

    assert result.type == "goal"


def test_memory_intake_locally_infers_concept() -> None:
    result = MemoryIntakeAgent().infer(body="Temporal memory means preserving when a thought changed.")

    assert result.type == "concept"
