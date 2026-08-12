"""An embedded, real-time admin dashboard for any Python service."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("dachshund")
except PackageNotFoundError:
    from dachshund._version import version as __version__

from dachshund.registry import Dashboard, init, shutdown
from dachshund.runtime.boot import Runtime

__all__ = [
    "Dashboard",
    "Runtime",
    "init",
    "shutdown",
]
