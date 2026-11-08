"""An embedded, real-time admin dashboard for any Python service."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("dachshund")
except PackageNotFoundError:
    from dachshund._version import version as __version__

from dachshund.actions import Context
from dachshund.layout import Column, Page, Row
from dachshund.registry import (
    Dashboard,
    action,
    add,
    column,
    default,
    emit,
    include,
    init,
    page,
    row,
    shutdown,
)

__all__ = [
    "Column",
    "Context",
    "Dashboard",
    "Page",
    "Row",
    "action",
    "add",
    "column",
    "default",
    "emit",
    "include",
    "init",
    "page",
    "row",
    "shutdown",
]
