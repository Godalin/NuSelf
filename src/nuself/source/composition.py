"""Source service composition."""

from nuself.config.settings import RuntimePaths
from nuself.source.repository import SourceRepository
from nuself.source.service import SourceService
from nuself.storage.contract import StorageBackend


def compose_source_service(paths: RuntimePaths, backend: StorageBackend) -> SourceService:
    return SourceService(SourceRepository(paths, backend=backend))
