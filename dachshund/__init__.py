"""An embedded, real-time admin dashboard for any Python service."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("dachshund")
except PackageNotFoundError:
    from dachshund._version import version as __version__

from dachshund.actions import Action, Context
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
from dachshund.runtime.boot import Runtime

__all__ = [
    "Action",
    "Column",
    "Context",
    "Dashboard",
    "Page",
    "Row",
    "Runtime",
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
