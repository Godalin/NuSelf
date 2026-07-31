from pathlib import Path

import pytest

from nuself.config import runtime_paths
from nuself.logs import LogComponent, read_log_events
from nuself.notification import NotificationOutbox
from nuself.persona.prompt_repo import PersonaPromptRepository
from nuself.reason.repository import ReasonRepository
from nuself.reflection.repository import ReflectionRepository
from nuself.storage import auto_backend
from nuself.trace.repository import TraceRepository

CASES: tuple[tuple[str, LogComponent], ...] = (
    ("persona_prompts", "persona"),
    ("reason_threads", "reasoning"),
    ("reflection_entries", "reflection"),
    ("notification_outbox", "outbox"),
    ("trace_nodes", "reasoning"),
    ("trace_edges", "reasoning"),
)


@pytest.mark.parametrize(("collection", "component"), CASES)
def test_repository_lists_report_corrupt_records(
    tmp_path: Path,
    collection: str,
    component: LogComponent,
) -> None:
    backend = auto_backend(tmp_path)
    backend.collection(collection).put(
        "bad_record",
        {"id": "bad_record", "invalid": True},
    )

    if collection == "persona_prompts":
        result = PersonaPromptRepository(
            collection=backend.collection("persona_prompts"),
            project_root=tmp_path,
        ).list()
    elif collection == "reason_threads":
        result = ReasonRepository(
            runtime_paths(tmp_path),
            backend=backend,
        ).list_threads()
    elif collection == "reflection_entries":
        result = ReflectionRepository(tmp_path, backend=backend).list()
    elif collection == "notification_outbox":
        result = NotificationOutbox(tmp_path, backend=backend).list()
    elif collection == "trace_nodes":
        result = TraceRepository(
            runtime_paths(tmp_path),
            backend=backend,
        ).list_traces()
    else:
        result = TraceRepository(
            runtime_paths(tmp_path),
            backend=backend,
        ).links_for(
            "trace_healthy"
        )

    assert len(result) == 0
    event = read_log_events(project_root=tmp_path, component=component)[-1]
    assert event.event == "record_decode_failed"
    assert event.metadata == {
        "collection": collection,
        "record_id": "bad_record",
    }
