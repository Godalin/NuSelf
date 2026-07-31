from __future__ import annotations

from pathlib import Path

import pytest

from nuself.memory.observation import MemoryObservation, MemoryObservationRepository
from nuself.storage import get_default_backend


def test_observe_is_durable_idempotent_and_producer_neutral(tmp_path: Path) -> None:
    repository = MemoryObservationRepository(get_default_backend(tmp_path))
    observation = MemoryObservation.create(
        source_ref="interaction:opaque",
        fragments=("user: remember this", "assistant: understood"),
    )

    assert repository.observe(observation) == observation
    assert repository.observe(observation) == observation
    assert repository.pending() == (observation,)

    repository.mark_processed(observation.id)

    assert repository.get(observation.id).status == "processed"
    assert repository.pending() == ()


def test_observe_rejects_identity_collision(tmp_path: Path) -> None:
    repository = MemoryObservationRepository(get_default_backend(tmp_path))
    original = MemoryObservation.create(
        source_ref="interaction:opaque",
        fragments=("first",),
    )
    repository.observe(original)

    with pytest.raises(ValueError, match="identity collision"):
        repository.observe(
            MemoryObservation(
                id=original.id,
                source_ref=original.source_ref,
                fragments=("different",),
                observed_at=original.observed_at,
            )
        )
