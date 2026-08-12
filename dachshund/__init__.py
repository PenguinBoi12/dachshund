"""An embedded, real-time admin dashboard for any Python service."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("dachshund")
except PackageNotFoundError:
    from dachshund._version import version as __version__

from dachshund.registry import (
    Dashboard,
    default,
    emit,
    graph,
    init,
    shutdown,
    widget,
)
from dachshund.runtime.boot import Runtime
from dachshund.storage.events import Event
from dachshund.widgets.base import Widget
from dachshund.widgets.builtin.line import LineGraph

__all__ = [
    "Dashboard",
    "Event",
    "LineGraph",
    "Runtime",
    "Widget",
    "default",
    "emit",
    "graph",
    "init",
    "shutdown",
    "widget",
]
