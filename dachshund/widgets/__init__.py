"""The cards the dashboard draws."""

from dachshund.widgets.base import WIDGETS, Widget, build
from dachshund.widgets.chart.bar import BarChart
from dachshund.widgets.chart.line import LineChart
from dachshund.widgets.chart.timeseries import TimeSeriesChart

__all__ = [
    "WIDGETS",
    "BarChart",
    "LineChart",
    "TimeSeriesChart",
    "Widget",
    "build",
]
