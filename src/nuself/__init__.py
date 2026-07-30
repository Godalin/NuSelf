"""NuSelf package."""

__all__ = ["__version__"]

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("nuself")
except PackageNotFoundError:  # pragma: no cover - source tree fallback
    __version__ = "0.3.0"
