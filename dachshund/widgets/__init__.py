"""The cards the dashboard draws."""

from dachshund.widgets.base import WIDGETS, Widget
from dachshund.widgets.button.button import Button
from dachshund.widgets.chart.bar import BarChart
from dachshund.widgets.chart.line import LineChart
from dachshund.widgets.chart.timeseries import TimeSeriesChart
from dachshund.widgets.number.number import Number
from dachshund.widgets.persistable import PersistableWidget
from dachshund.widgets.table.table import Table
from dachshund.widgets.text.text import Text

__all__ = [
    "WIDGETS",
    "BarChart",
    "Button",
    "LineChart",
    "Number",
    "PersistableWidget",
    "Table",
    "Text",
    "TimeSeriesChart",
    "Widget",
]
