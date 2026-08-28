import pytest

from dachshund.storage.events import Event
from dachshund.widgets.chart.line import LineChart


def test_a_line_without_an_x__expect_type_error() -> None:
    with pytest.raises(TypeError, match="x"):
        LineChart("perf", source="perf")  # type: ignore[call-arg]


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
