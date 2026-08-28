import logging
from datetime import datetime, timedelta, timezone

import pytest

from dachshund.storage.events import Event
from dachshund.widgets.chart.timeseries import TimeSeriesChart


def test_a_timeseries_without_an_x__expect_no_error() -> None:
    assert TimeSeriesChart("latency", source="latency").x == ""


def test_a_chart_without_a_y_field__expect_value_error() -> None:
    with pytest.raises(ValueError, match="at least one y field"):
        TimeSeriesChart("perf", source="perf", y=[])


def test_series__expect_a_tuple_however_y_was_given() -> None:
    assert TimeSeriesChart("a", source="a").series == ("value",)
    assert TimeSeriesChart("b", source="b", y="ms").series == ("ms",)
    assert TimeSeriesChart("c", source="c", y=["p50", "p95"]).series == ("p50", "p95")


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
