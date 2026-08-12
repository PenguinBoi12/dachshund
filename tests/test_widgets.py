from datetime import datetime, timedelta, timezone

import pytest

from dachshund.storage.events import Event
from dachshund.widgets.base import Widget
from dachshund.widgets.builtin.line import LineGraph


def test_label__expect_the_name_when_untitled() -> None:
    assert LineGraph("requests_per_sec", source="request").label == "requests per sec"


def test_label__expect_the_title_when_given() -> None:
    graph = LineGraph("latency", source="latency", title="Response time")

    assert graph.label == "Response time"


@pytest.mark.parametrize("size", [0, 4])
def test_widget_with_a_size_off_the_grid__expect_value_error(size: int) -> None:
    with pytest.raises(ValueError, match="1 to 3 columns"):
        Widget("latency", source="latency", size=size)


def test_render__expect_the_columns_uplot_draws() -> None:
    graph = LineGraph("latency", source="latency")
    now = datetime.now(tz=timezone.utc)
    events = [
        Event("latency", {"value": 96}, at=now - timedelta(seconds=1)),
        Event("latency", {"value": 108}, at=now),
    ]

    assert graph.render(events) == {
        "x": [(now - timedelta(seconds=1)).timestamp(), now.timestamp()],
        "y": [96.0, 108.0],
    }


def test_update__expect_a_single_point() -> None:
    graph = LineGraph("latency", source="latency")
    now = datetime.now(tz=timezone.utc)

    assert graph.update(Event("latency", {"value": 96}, at=now)) == {
        "x": now.timestamp(),
        "y": 96.0,
    }


def test_value_without_the_field__expect_one_so_events_can_be_counted() -> None:
    graph = LineGraph("request", source="request")

    assert graph.value(Event("request")) == 1.0


def test_value_of_another_field__expect_that_field() -> None:
    graph = LineGraph("latency", source="latency", field="ms")

    assert graph.value(Event("latency", {"ms": 96})) == 96.0


def test_type_and_op__expect_an_appending_line() -> None:
    assert LineGraph.op == "append"
    assert LineGraph.type == "line"
