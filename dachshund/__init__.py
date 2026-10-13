"""An embedded, real-time admin dashboard for any Python service."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("dachshund")
except PackageNotFoundError:
    from dachshund._version import version as __version__

from dachshund.actions import Action, Context
from dachshund.layout import Page
from dachshund.registry import (
    Dashboard,
    default,
    emit,
    chart,
    init,
    page,
    row,
    shutdown,
    widget,
    action,
)
from dachshund.runtime.boot import Runtime
from dachshund.storage.events import Event
from dachshund.widgets.base import Widget
from dachshund.widgets.button.button import Button
from dachshund.widgets.chart.bar import BarChart
from dachshund.widgets.chart.line import LineChart
from dachshund.widgets.chart.timeseries import TimeSeriesChart
from dachshund.widgets.number.number import Number
from dachshund.widgets.table.table import Table
from dachshund.widgets.text.text import Text

__all__ = [
    "Action",
    "BarChart",
    "Button",
    "Context",
    "Dashboard",
    "Event",
    "LineChart",
    "Number",
    "Page",
    "Runtime",
    "Table",
    "Text",
    "TimeSeriesChart",
    "Widget",
    "action",
    "chart",
    "default",
    "emit",
    "init",
    "page",
    "row",
    "shutdown",
    "widget",
]
