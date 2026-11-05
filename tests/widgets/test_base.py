from pathlib import Path

import pytest

from dachshund.widgets.base import WIDGETS, Widget
from dachshund.widgets.button.button import Button
from dachshund.widgets.chart.bar import BarChart
from dachshund.widgets.chart.line import LineChart
from dachshund.widgets.chart.timeseries import TimeSeriesChart
from dachshund.widgets.number.number import Number
from dachshund.widgets import KeyedWidget
from dachshund.widgets.table.table import Table

FIXTURE_SCRIPT = Path(__file__).parent.parent / "fixtures" / "gauge.js"


def test_widget_without_a_source__expect_its_name() -> None:
    assert Widget("latency").source == "latency"


def test_widget_with_a_source__expect_it_kept() -> None:
    assert Widget("latency", source="ping").source == "ping"


def test_an_intermediate_base_without_its_own_type__expect_it_not_registered() -> None:
    class Base(Widget):
        pass

    assert Base not in WIDGETS.values()
    assert KeyedWidget not in WIDGETS.values()


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
