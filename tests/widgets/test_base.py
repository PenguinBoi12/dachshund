from pathlib import Path

import pytest

from dachshund.widgets.base import WIDGETS, Widget, build
from dachshund.widgets.button.button import Button
from dachshund.widgets.chart.bar import BarChart
from dachshund.widgets.chart.line import LineChart
from dachshund.widgets.chart.timeseries import TimeSeriesChart
from dachshund.widgets.number.number import Number
from dachshund.widgets.state import KeyedWidget
from dachshund.widgets.table.table import Table

FIXTURE_SCRIPT = Path(__file__).parent.parent / "fixtures" / "gauge.js"


@pytest.mark.parametrize("size", [0, 4])
def test_widget_with_a_size_off_the_grid__expect_value_error(size: int) -> None:
    with pytest.raises(ValueError, match="1 to 3 columns"):
        Widget("latency", source="latency", size=size)


def test_widget_snapshot_by_default__expect_none() -> None:
    assert Widget("latency", source="latency").snapshot() is None


def test_widget_default__expect_rollup_unsafe() -> None:
    assert Widget.rollup_safe is False


def test_line_and_timeseries__expect_rollup_safe() -> None:
    assert LineChart.rollup_safe is True
    assert TimeSeriesChart.rollup_safe is True


def test_table_and_bar__expect_rollup_unsafe() -> None:
    assert Table.rollup_safe is False
    assert BarChart.rollup_safe is False


def test_keyed_widget__expect_table_and_bar_share_it() -> None:
    assert issubclass(Table, KeyedWidget)
    assert issubclass(BarChart, KeyedWidget)


def test_builtin_chart_types__expect_them_registered() -> None:
    assert WIDGETS["bar"] is BarChart
    assert WIDGETS["line"] is LineChart
    assert WIDGETS["timeseries"] is TimeSeriesChart
    assert WIDGETS["number"] is Number
    assert WIDGETS["button"] is Button
    assert WIDGETS["table"] is Table


def test_a_widget_subclass__expect_it_registered_under_its_type() -> None:
    class Gauge(Widget):
        type = "custom_test_gauge"

    assert WIDGETS["custom_test_gauge"] is Gauge


def test_build_of_a_custom_type__expect_it_constructed() -> None:
    class Meter(Widget):
        type = "custom_test_meter"

    widget = build("dial", type="custom_test_meter")

    assert isinstance(widget, Meter)
    assert widget.source == "dial"


def test_widget_script_and_style_default__expect_none() -> None:
    assert Widget.script is None
    assert Widget.style is None


def test_a_widget_with_a_missing_script__expect_a_clear_error() -> None:
    with pytest.raises(FileNotFoundError, match="nope.js"):

        class BadGauge(Widget):
            type = "custom_test_bad_gauge"
            script = Path(__file__).parent / "nope.js"


def test_a_widget_with_a_script__expect_it_registered() -> None:
    class Gauge(Widget):
        type = "custom_test_gauge_with_script"
        script = FIXTURE_SCRIPT

    assert WIDGETS["custom_test_gauge_with_script"].script == FIXTURE_SCRIPT


def test_builtin_charts__expect_them_sharing_one_script_and_style() -> None:
    # The three chart types are one cohesive rendering module, not three.
    assert LineChart.script == BarChart.script == TimeSeriesChart.script
    assert LineChart.style == BarChart.style == TimeSeriesChart.style
    assert LineChart.script is not None and LineChart.script.is_file()
    assert LineChart.style is not None and LineChart.style.is_file()


def test_type_and_op__expect_each_chart_to_declare_its_own() -> None:
    assert (TimeSeriesChart.type, TimeSeriesChart.op) == ("timeseries", "append")
    assert (LineChart.type, LineChart.op) == ("line", "append")
    assert (BarChart.type, BarChart.op) == ("bar", "replace")
