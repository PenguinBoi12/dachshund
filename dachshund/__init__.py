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
    chart,
    init,
    shutdown,
    widget,
)
from dachshund.runtime.boot import Runtime
from dachshund.storage.events import Event
from dachshund.widgets.base import Widget
from dachshund.widgets.chart.bar import BarChart
from dachshund.widgets.chart.line import LineChart
from dachshund.widgets.chart.timeseries import TimeSeriesChart

__all__ = [
    "BarChart",
    "Dashboard",
    "Event",
    "LineChart",
    "Runtime",
    "TimeSeriesChart",
    "Widget",
    "chart",
    "default",
    "emit",
    "init",
    "shutdown",
    "widget",
]
