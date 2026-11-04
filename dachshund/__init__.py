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
from dachshund.storage.events import Event
from dachshund.widgets.base import Widget
from dachshund.widgets.button.button import Button
from dachshund.widgets.chart.bar import BarChart
from dachshund.widgets.chart.line import LineChart
from dachshund.widgets.chart.timeseries import TimeSeriesChart
from dachshund.widgets.number.number import Number
from dachshund.widgets.persistable import PersistableWidget
from dachshund.widgets.query import TableQuery
from dachshund.widgets.table.table import Table
from dachshund.widgets.text.text import Text

__all__ = [
    "Action",
    "BarChart",
    "Button",
    "Column",
    "Context",
    "Dashboard",
    "Event",
    "LineChart",
    "Number",
    "Page",
    "PersistableWidget",
    "Row",
    "Runtime",
    "Table",
    "TableQuery",
    "Text",
    "TimeSeriesChart",
    "Widget",
    "action",
    "column",
    "default",
    "emit",
    "include",
    "init",
    "page",
    "row",
    "shutdown",
]
