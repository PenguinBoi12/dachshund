import logging
from datetime import datetime, timedelta, timezone

import pytest

from dachshund.storage.events import Event
from dachshund.widgets.base import WIDGETS, Widget, build
from dachshund.widgets.chart.bar import BarChart
from dachshund.widgets.chart.line import LineChart
from dachshund.widgets.chart.timeseries import TimeSeriesChart


@pytest.mark.parametrize("size", [0, 4])
def test_widget_with_a_size_off_the_grid__expect_value_error(size: int) -> None:
    with pytest.raises(ValueError, match="1 to 3 columns"):
        Widget("latency", source="latency", size=size)


def test_builtin_chart_types__expect_them_registered() -> None:
    assert WIDGETS["bar"] is BarChart
    assert WIDGETS["line"] is LineChart
    assert WIDGETS["timeseries"] is TimeSeriesChart


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


def test_a_line_without_an_x__expect_type_error() -> None:
    with pytest.raises(TypeError, match="x"):
        LineChart("perf", source="perf")  # type: ignore[call-arg]


def test_a_timeseries_without_an_x__expect_no_error() -> None:
    assert TimeSeriesChart("latency", source="latency").x == ""


def test_a_chart_without_a_y_field__expect_value_error() -> None:
    with pytest.raises(ValueError, match="at least one y field"):
        TimeSeriesChart("perf", source="perf", y=[])


def test_series__expect_a_tuple_however_y_was_given() -> None:
    assert TimeSeriesChart("a", source="a").series == ("value",)
    assert TimeSeriesChart("b", source="b", y="ms").series == ("ms",)
    assert TimeSeriesChart("c", source="c", y=["p50", "p95"]).series == ("p50", "p95")


def test_type_and_op__expect_each_chart_to_declare_its_own() -> None:
    assert (TimeSeriesChart.type, TimeSeriesChart.op) == ("timeseries", "append")
    assert (LineChart.type, LineChart.op) == ("line", "append")
    assert (BarChart.type, BarChart.op) == ("bar", "replace")


def test_timeseries_render__expect_the_columns_uplot_draws() -> None:
    chart = TimeSeriesChart("latency", source="latency")
    now = datetime.now(tz=timezone.utc)
    events = [
        Event("latency", {"value": 96}, at=now - timedelta(seconds=1)),
        Event("latency", {"value": 108}, at=now),
    ]

    assert chart.render(events) == {
        "series": ["value"],
        "x": [(now - timedelta(seconds=1)).timestamp(), now.timestamp()],
        "y": [[96.0, 108.0]],
    }


def test_timeseries_update__expect_a_row_placed_in_time() -> None:
    chart = TimeSeriesChart("latency", source="latency")
    now = datetime.now(tz=timezone.utc)

    assert chart.update(Event("latency", {"value": 96}, at=now)) == {
        "x": now.timestamp(),
        "y": [96.0],
    }


def test_render_with_several_y_fields__expect_a_line_each() -> None:
    chart = TimeSeriesChart("perf", source="perf", y=["p50", "p95"])
    now = datetime.now(tz=timezone.utc)
    events = [
        Event("perf", {"p50": 10, "p95": 40}, at=now - timedelta(seconds=1)),
        Event("perf", {"p50": 12, "p95": 44}, at=now),
    ]

    assert chart.render(events) == {
        "series": ["p50", "p95"],
        "x": [(now - timedelta(seconds=1)).timestamp(), now.timestamp()],
        "y": [[10.0, 12.0], [40.0, 44.0]],
    }


def test_update_with_several_y_fields__expect_one_row() -> None:
    chart = TimeSeriesChart("perf", source="perf", y=["p50", "p95"])
    now = datetime.now(tz=timezone.utc)

    assert chart.update(Event("perf", {"p50": 10, "p95": 40}, at=now)) == {
        "x": now.timestamp(),
        "y": [10.0, 40.0],
    }


def test_line_render__expect_x_and_y_read_from_the_event() -> None:
    chart = LineChart("throughput", source="throughput", x="requests", y="latency")
    events = [
        Event("throughput", {"requests": 120, "latency": 96}),
        Event("throughput", {"requests": 240, "latency": 108}),
    ]

    assert chart.render(events) == {
        "series": ["latency"],
        "x": [120.0, 240.0],
        "y": [[96.0, 108.0]],
    }


def test_line_at_without_the_field__expect_nowhere_to_sit() -> None:
    chart = LineChart("throughput", source="throughput", x="requests")

    assert chart.at(Event("throughput")) is None


def test_render_with_an_unreadable_x__expect_the_row_dropped() -> None:
    chart = LineChart("perf", source="perf", x="requests", y="ms")
    events = [
        Event("perf", {"requests": 120, "ms": 96}),
        Event("perf", {"requests": "many", "ms": 108}),
    ]

    assert chart.render(events) == {
        "series": ["ms"],
        "x": [120.0],
        "y": [[96.0]],
    }


def test_update_with_an_unreadable_x__expect_nothing_to_draw() -> None:
    chart = LineChart("perf", source="perf", x="requests")

    assert chart.update(Event("perf", {"requests": "many"})) is None


def test_value_of_something_unreadable__expect_a_gap() -> None:
    chart = TimeSeriesChart("latency", source="latency")

    assert chart.value(Event("latency", {"value": "fast"}), "value") is None


def test_value_of_a_field_the_event_lacks__expect_a_gap() -> None:
    chart = TimeSeriesChart("latency", source="latency")

    assert chart.value(Event("latency", {"ms": 96}), "value") is None


def test_render_with_an_unreadable_value__expect_a_gap_in_the_line() -> None:
    chart = TimeSeriesChart("latency", source="latency")
    now = datetime.now(tz=timezone.utc)
    events = [
        Event("latency", {"value": 96}, at=now - timedelta(seconds=1)),
        Event("latency", {"value": "fast"}, at=now),
    ]

    assert chart.render(events)["y"] == [[96.0, None]]


def test_render_with_one_unreadable_series__expect_the_others_kept() -> None:
    chart = TimeSeriesChart("perf", source="perf", y=["p50", "p95"])

    assert chart.render([Event("perf", {"p50": 10, "p95": "slow"})])["y"] == [
        [10.0],
        [None],
    ]


def test_warn__expect_one_line_however_often_the_field_arrives(
    caplog: pytest.LogCaptureFixture,
) -> None:
    chart = TimeSeriesChart("latency", source="latency")

    with caplog.at_level(logging.WARNING, logger="dachshund"):
        for _ in range(5):
            chart.value(Event("latency", {"value": "fast"}), "value")

    assert caplog.text.count("is not a number") == 1


def test_bar_render__expect_a_total_per_category() -> None:
    chart = BarChart("weight", source="weight", x="name", y="ms")
    events = [
        Event("weight", {"name": "/ban", "ms": 96}),
        Event("weight", {"name": "/help", "ms": 4}),
        Event("weight", {"name": "/ban", "ms": 4}),
    ]

    assert chart.render(events) == {
        "series": ["ms"],
        "x": ["/ban", "/help"],
        "y": [[100.0, 4.0]],
    }


def test_bar_counting__expect_the_emitted_ones_totalled() -> None:
    chart = BarChart("commands", source="commands", x="name")
    events = [
        Event("commands", {"name": "/ban", "value": 1}),
        Event("commands", {"name": "/ban", "value": 1}),
        Event("commands", {"name": "/help", "value": 1}),
    ]

    assert chart.render(events) == {
        "series": ["value"],
        "x": ["/ban", "/help"],
        "y": [[2.0, 1.0]],
    }


def test_bar_render_without_the_category__expect_one_unlabelled_bar() -> None:
    chart = BarChart("commands", source="commands", x="name")

    assert chart.render([Event("commands", {"value": 1})]) == {
        "series": ["value"],
        "x": ["—"],
        "y": [[1.0]],
    }


def test_bar_render_with_an_unreadable_value__expect_it_left_out() -> None:
    chart = BarChart("weight", source="weight", x="name", y="ms")
    events = [
        Event("weight", {"name": "/ban", "ms": 96}),
        Event("weight", {"name": "/ban", "ms": "slow"}),
    ]

    assert chart.render(events) == {
        "series": ["ms"],
        "x": ["/ban"],
        "y": [[96.0]],
    }


def test_bar_render_of_an_event_carrying_nothing__expect_it_left_out() -> None:
    chart = BarChart("commands", source="commands", x="name")

    assert chart.render([Event("commands", {"name": "/ban"})]) == {
        "series": ["value"],
        "x": [],
        "y": [[]],
    }
