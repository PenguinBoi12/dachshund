import logging
import threading
from collections.abc import Iterator
from typing import Any, Callable
from urllib.request import urlopen

import pytest

import dachshund
from dachshund import registry
from dachshund.registry import Dashboard
from dachshund.widgets.chart.bar import BarChart
from dachshund.widgets.chart.line import LineChart
from dachshund.widgets.chart.timeseries import TimeSeriesChart


@pytest.fixture(autouse=True)
def no_dashboard_left_behind() -> Iterator[None]:
    yield
    dachshund.shutdown()
    registry._dashboard = None


def test_dashboard_start__expect_the_dashboard_served() -> None:
    dashboard = Dashboard(
        "Ada", description="Code Society's Matrix bot", port=0, path=":memory:"
    )
    dashboard.start()

    try:
        assert dashboard.is_running
        assert dashboard.name == "Ada"
        assert dashboard.description == "Code Society's Matrix bot"

        with urlopen(dashboard.url) as response:
            assert response.status == 200
    finally:
        dashboard.stop()

    assert not dashboard.is_running


def test_init_when_already_running__expect_the_same_dashboard() -> None:
    dashboard = dachshund.init("Ada", port=0, path=":memory:")

    assert dachshund.init("Ada", port=0, path=":memory:") is dashboard
    assert dashboard.is_running

    dachshund.shutdown()

    assert not dashboard.is_running


def test_init_with_a_name_and_description__expect_them_kept() -> None:
    dashboard = dachshund.init(
        "Ada", description="Code Society's Matrix bot", port=0, path=":memory:"
    )

    assert dashboard.name == "Ada"
    assert dashboard.description == "Code Society's Matrix bot"


def test_init_with_another_address__expect_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    dashboard = dachshund.init("Ada", port=0, path=":memory:")

    with caplog.at_level(logging.WARNING, logger="dachshund"):
        assert dachshund.init("Ada", port=9999, path=":memory:") is dashboard

    assert "already running" in caplog.text
    assert dashboard.runtime.requested_port == 0


def test_init_with_a_different_storage_path__expect_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    dachshund.default(path=":memory:")

    with caplog.at_level(logging.WARNING, logger="dachshund"):
        dashboard = dachshund.init("Ada", port=0, path="somewhere-else.db")

    assert "already opened" in caplog.text
    assert dashboard.path == ":memory:"


class FakeStorage:
    """A `Storage` that never gets used, just needs a distinct identity."""

    async def save(self, key: str, value: dict[str, object]) -> None:
        pass

    async def load(self, key: str) -> dict[str, object] | None:
        return None


def test_init_with_a_different_storage__expect_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    dachshund.default(path=":memory:")

    with caplog.at_level(logging.WARNING, logger="dachshund"):
        dachshund.init("Ada", port=0, path=":memory:", storage=FakeStorage())

    assert "already set up its own storage" in caplog.text


def test_init_from_concurrent_callers__expect_a_single_dashboard() -> None:
    dashboards: list[Dashboard] = []
    start = threading.Barrier(4)

    def racer() -> None:
        start.wait()
        dashboards.append(dachshund.init("Ada", port=0, path=":memory:"))

    threads = [threading.Thread(target=racer) for _ in range(4)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)

    assert len(dashboards) == 4
    assert len({id(dashboard) for dashboard in dashboards}) == 1


def test_init_after_a_manual_stop__expect_a_single_exit_hook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hooks: list[Callable[..., Any]] = []

    def forget(hook: Callable[..., Any]) -> None:
        if hook in hooks:
            hooks.remove(hook)

    monkeypatch.setattr(registry.atexit, "register", hooks.append)
    monkeypatch.setattr(registry.atexit, "unregister", forget)

    dachshund.init("Ada", port=0, path=":memory:").stop()
    dachshund.init("Ada", port=0, path=":memory:")

    assert len(hooks) == 1


def test_shutdown_without_a_dashboard__expect_no_error() -> None:
    dachshund.shutdown()


def test_init_without_a_name__expect_a_dashboard_anyway() -> None:
    dashboard = dachshund.init(port=0, path=":memory:")

    assert dashboard.is_running
    assert dashboard.name is None


@pytest.mark.parametrize("name", ["", "   "])
def test_dashboard_with_a_blank_name__expect_value_error(name: str) -> None:
    with pytest.raises(ValueError, match="cannot be blank"):
        Dashboard(name)


def test_chart__expect_it_registered_with_its_own_name_as_source() -> None:
    dashboard = Dashboard(path=":memory:")
    graph = dashboard.chart("latency", type="timeseries", size=2)

    assert dashboard.widgets == {"latency": graph}
    assert graph.source == "latency"
    assert graph.size == 2


def test_add_a_duplicate_name__expect_value_error() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.chart("latency", type="timeseries")

    with pytest.raises(ValueError, match="already exists"):
        dashboard.chart("latency", type="timeseries")


def test_watching__expect_the_widgets_fed_by_a_source() -> None:
    dashboard = Dashboard(path=":memory:")
    graph = dashboard.chart("latency", type="timeseries", source="request")
    dashboard.chart("errors", type="timeseries")

    assert dashboard.watching("request") == [graph]


def test_drain__expect_the_queued_events_returned_oldest_first() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.emit("latency", value=96)
    dashboard.emit("latency", value=108)

    drained = dashboard.drain()

    assert [event.payload["value"] for event in drained] == [96, 108]
    assert dashboard.drain() == []


@pytest.mark.asyncio
async def test_drain_then_append__expect_the_events_kept() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.emit("latency", value=96)
    dashboard.emit("latency", value=108)

    await dashboard.events.append(dashboard.drain())

    assert len(await dashboard.events.events("latency")) == 2


def test_emit_past_the_queue_size__expect_the_extras_dropped() -> None:
    dashboard = Dashboard(path=":memory:")

    for _ in range(registry.QUEUE_SIZE + 5):
        dashboard.emit("latency", value=96)

    assert dashboard.dropped == 5
    assert len(dashboard.drain()) == registry.QUEUE_SIZE


def test_emit_from_another_thread__expect_it_queued() -> None:
    dashboard = Dashboard(path=":memory:")
    thread = threading.Thread(
        target=dashboard.emit, args=("latency",), kwargs={"value": 96}
    )

    thread.start()
    thread.join(5)

    assert len(dashboard.drain()) == 1


def test_module_level_registration__expect_the_default_dashboard() -> None:
    dachshund.default(path=":memory:")
    graph = dachshund.chart("latency", type="timeseries")
    dachshund.emit("latency", value=96)

    assert dachshund.default().widgets == {"latency": graph}
    assert len(dachshund.default().drain()) == 1


def test_widgets_registered_before_init__expect_them_kept() -> None:
    dachshund.default(path=":memory:")
    graph = dachshund.chart("latency", type="timeseries")
    dashboard = dachshund.init("Ada", port=0, path=":memory:")

    assert dashboard.widgets == {"latency": graph}


def test_widget__expect_a_widget_of_the_named_type() -> None:
    dashboard = Dashboard(path=":memory:")
    widget = dashboard.widget("latency", type="timeseries", size=2)

    assert isinstance(widget, TimeSeriesChart)
    assert dashboard.widgets == {"latency": widget}
    assert widget.source == "latency"


def test_widget_of_an_unknown_type__expect_value_error() -> None:
    with pytest.raises(ValueError, match="no 'heatmap' widget type"):
        Dashboard(path=":memory:").widget("heat", type="heatmap")


def test_emit_with_several_fields__expect_them_all_kept() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.emit("command", name="/ban", issuer="tomcat")

    assert dashboard.drain()[0].payload == {"name": "/ban", "issuer": "tomcat"}


def test_emit_of_a_field_named_source__expect_no_collision() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.emit("request", source="webhook")

    assert dashboard.drain()[0].payload == {"source": "webhook"}


def test_chart_of_an_unknown_type__expect_value_error() -> None:
    with pytest.raises(ValueError, match="no 'pie' widget type"):
        Dashboard(path=":memory:").chart("latency", type="pie")


def test_persisting_chart_without_storage__expect_value_error() -> None:
    with pytest.raises(ValueError, match="no storage is configured"):
        Dashboard(path=":memory:").chart("commands", type="bar", x="name", persist=True)


def test_chart__expect_a_line_by_default() -> None:
    graph = Dashboard(path=":memory:").chart("throughput", x="requests")

    assert isinstance(graph, LineChart)


def test_chart_typed_as_a_line__expect_x_and_y_fields() -> None:
    graph = Dashboard(path=":memory:").chart(
        "throughput", type="line", x="requests", y="latency"
    )

    assert isinstance(graph, LineChart)
    assert (graph.x, graph.y) == ("requests", "latency")


def test_timeseries_given_an_x__expect_value_error() -> None:
    with pytest.raises(ValueError, match="takes its x from when events happen"):
        Dashboard(path=":memory:").chart("latency", type="timeseries", x="requests")


def test_chart_typed_as_a_bar__expect_x_naming_its_category() -> None:
    chart = Dashboard(path=":memory:").chart("commands", type="bar", x="name")

    assert isinstance(chart, BarChart)
    assert chart.x == "name"
