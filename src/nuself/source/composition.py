"""Source service composition."""

from dataclasses import dataclass

from nuself.config.settings import RuntimePaths
from nuself.source.importer import SourceImporter
from nuself.source.repository import SourceRepository
from nuself.source.service import SourceService
from nuself.storage.contract import StorageBackend


@dataclass(frozen=True)
class SourceServices:
    """Identity-coupled query and append-only ingestion capabilities."""

    query: SourceService
    importer: SourceImporter


def compose_source_services(
    paths: RuntimePaths,
    backend: StorageBackend,
) -> SourceServices:
    repository = SourceRepository(paths, backend=backend)
    return SourceServices(
        query=SourceService(repository),
        importer=SourceImporter(repository),
    )
