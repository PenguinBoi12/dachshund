"""The cards the dashboard draws."""

from dachshund.widgets.aggregate import AggregatedWidget
from dachshund.widgets.base import Widget
from dachshund.widgets.button.button import Button
from dachshund.widgets.chart.bar import BarChart
from dachshund.widgets.chart.line import LineChart
from dachshund.widgets.chart.timeseries import TimeSeriesChart
from dachshund.widgets.logs.logs import Logs
from dachshund.widgets.number.number import Number
from dachshund.widgets.persistable import PersistableWidget
from dachshund.widgets.query import TableQuery
from dachshund.widgets.state import KeyedWidget
from dachshund.widgets.table.table import Table
from dachshund.widgets.text.text import Text

__all__ = [
    "AggregatedWidget",
    "BarChart",
    "Button",
    "KeyedWidget",
    "LineChart",
    "Logs",
    "Number",
    "PersistableWidget",
    "Table",
    "TableQuery",
    "Text",
    "TimeSeriesChart",
    "Widget",
]
