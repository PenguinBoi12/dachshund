import logging
import threading
import time
from collections.abc import Iterator
from typing import Any, Callable
from urllib.request import urlopen

import pytest

import dachshund
from dachshund import registry
from dachshund.layout import Column, Page, Row
from dachshund.registry import Dashboard
from dachshund.runtime.ws import PUMP_INTERVAL
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


def test_init_with_context__expect_it_set() -> None:
    dashboard = dachshund.init(port=0, path=":memory:", context={"bot": "b"})

    assert dashboard.context == {"bot": "b"}


def test_init_with_context_twice__expect_keys_merged() -> None:
    dashboard = dachshund.init(port=0, path=":memory:", context={"bot": "b"})
    dachshund.shutdown()
    dachshund.init(port=0, path=":memory:", context={"db": "d"})

    assert dashboard.context == {"bot": "b", "db": "d"}


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


class SeededStorage:
    """An in-memory `Storage`, pre-loadable with a value before `start()`."""

    def __init__(self) -> None:
        self.saved: dict[str, dict[str, object]] = {}

    async def save(self, key: str, value: dict[str, object]) -> None:
        self.saved[key] = value

    async def load(self, key: str) -> dict[str, object] | None:
        return self.saved.get(key)


def test_init_with_a_different_storage__expect_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    dachshund.default(path=":memory:", storage=FakeStorage())

    with caplog.at_level(logging.WARNING, logger="dachshund"):
        dachshund.init("Ada", port=0, path=":memory:", storage=FakeStorage())

    assert "already set up its own storage" in caplog.text


def test_default_storage_supplied_after_the_fact__expect_it_adopted() -> None:
    dachshund.default(path=":memory:")
    storage = FakeStorage()

    dashboard = dachshund.default(storage=storage)

    assert dashboard.storage is storage


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


def test_add__expect_the_widget_registered_and_returned() -> None:
    dashboard = Dashboard(path=":memory:")
    graph = dashboard.add(TimeSeriesChart("latency"))

    assert dashboard.widgets == {"latency": graph}
    assert graph.source == "latency"


def test_add_a_duplicate_name__expect_value_error() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.add(TimeSeriesChart("latency"))

    with pytest.raises(ValueError, match="already exists"):
        dashboard.add(TimeSeriesChart("latency"))


def test_watching__expect_the_widgets_fed_by_a_source() -> None:
    dashboard = Dashboard(path=":memory:")
    graph = dashboard.add(TimeSeriesChart("latency", source="request"))
    dashboard.add(TimeSeriesChart("errors"))

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


def test_emit_past_the_queue_size__expect_one_warning_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    dashboard = Dashboard(path=":memory:")

    with caplog.at_level(logging.WARNING, logger="dachshund"):
        for _ in range(registry.QUEUE_SIZE + 5):
            dashboard.emit("latency", value=96)

    assert caplog.text.count("event queue is full") == 1


def test_emit_after_the_queue_drains__expect_a_new_streak_logged_again(
    caplog: pytest.LogCaptureFixture,
) -> None:
    dashboard = Dashboard(path=":memory:")

    with caplog.at_level(logging.WARNING, logger="dachshund"):
        for _ in range(registry.QUEUE_SIZE + 1):
            dashboard.emit("latency", value=96)

        dashboard.drain()
        caplog.clear()

        for _ in range(registry.QUEUE_SIZE + 1):
            dashboard.emit("latency", value=96)

    assert caplog.text.count("event queue is full") == 1


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
    graph = dachshund.add(TimeSeriesChart("latency"))
    dachshund.emit("latency", value=96)

    assert dachshund.default().widgets == {"latency": graph}
    assert len(dachshund.default().drain()) == 1


def test_widgets_registered_before_init__expect_them_kept() -> None:
    dachshund.default(path=":memory:")
    graph = dachshund.add(TimeSeriesChart("latency"))
    dashboard = dachshund.init("Ada", port=0, path=":memory:")

    assert dashboard.widgets == {"latency": graph}


def test_widget__expect_a_widget_of_the_named_type() -> None:
    dashboard = Dashboard(path=":memory:")
    widget = dashboard.add(TimeSeriesChart("latency"))

    assert isinstance(widget, TimeSeriesChart)
    assert dashboard.widgets == {"latency": widget}
    assert widget.source == "latency"


def test_emit_with_several_fields__expect_them_all_kept() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.emit("command", name="/ban", issuer="tomcat")

    assert dashboard.drain()[0].payload == {"name": "/ban", "issuer": "tomcat"}


def test_emit_of_a_field_named_source__expect_no_collision() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.emit("request", source="webhook")

    assert dashboard.drain()[0].payload == {"source": "webhook"}


def test_persisting_chart_without_storage__expect_value_error() -> None:
    with pytest.raises(ValueError, match="no storage is configured"):
        Dashboard(path=":memory:").add(BarChart("commands", x="name", persist=True))


def test_persisting_chart_registered_after_start__expect_it_hydrated_anyway() -> None:
    storage = SeededStorage()
    storage.saved["commands"] = {"entries": {"/ban": 3}, "seen_at": {}}
    dashboard = Dashboard(path=":memory:", storage=storage, port=0)  # type: ignore[arg-type]
    dashboard.start()

    try:
        commands = dashboard.add(BarChart("commands", x="name", persist=True))
        time.sleep(PUMP_INTERVAL * 2)

        assert commands.state.entries == {"/ban": 3}  # type: ignore[attr-defined]
    finally:
        dashboard.stop()


def test_chart__expect_a_line_by_default() -> None:
    graph = Dashboard(path=":memory:").add(LineChart("throughput", x="requests"))

    assert isinstance(graph, LineChart)


def test_chart_typed_as_a_line__expect_x_and_y_fields() -> None:
    graph = Dashboard(path=":memory:").add(
        LineChart("throughput", x="requests", y="latency")
    )

    assert isinstance(graph, LineChart)
    assert (graph.x, graph.y) == ("requests", "latency")


def test_timeseries_given_an_x__expect_value_error() -> None:
    with pytest.raises(ValueError, match="takes its x from when events happen"):
        Dashboard(path=":memory:").add(TimeSeriesChart("latency", x="requests"))


def test_chart_typed_as_a_bar__expect_x_naming_its_category() -> None:
    chart = Dashboard(path=":memory:").add(BarChart("commands", x="name"))

    assert isinstance(chart, BarChart)
    assert chart.x == "name"


def test_page__expect_it_created_with_a_title() -> None:
    dashboard = Dashboard(path=":memory:")
    page = dashboard.page("errors", title="Errors")

    assert dashboard.pages == {"errors": page}
    assert (page.name, page.title) == ("errors", "Errors")


def test_page_called_again__expect_the_same_page_retitled() -> None:
    dashboard = Dashboard(path=":memory:")
    first = dashboard.page("errors")
    second = dashboard.page("errors", title="Errors")

    assert first is second
    assert second.title == "Errors"


def test_row_of_an_unknown_widget__expect_value_error() -> None:
    with pytest.raises(ValueError, match="No widgets named: ghost"):
        Dashboard(path=":memory:").row("ghost")


def test_row__expect_it_recorded_on_the_named_page() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.add(TimeSeriesChart("latency"))
    dashboard.add(TimeSeriesChart("errors"))

    dashboard.row("latency", "errors", page="requests")

    assert dashboard.pages["requests"].rows == [Row(["latency", "errors"])]


def test_layout_with_nothing_declared__expect_every_widget_in_the_flow() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.add(TimeSeriesChart("latency"))
    dashboard.add(TimeSeriesChart("errors"))

    assert dashboard.layout() == ([], ["latency", "errors"])


def test_layout_with_some_widgets_placed__expect_leftovers_in_the_flow() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.add(TimeSeriesChart("latency"))
    dashboard.add(TimeSeriesChart("errors"))
    dashboard.add(TimeSeriesChart("cpu"))

    dashboard.row("errors")

    assert dashboard.layout() == ([Row(["errors"])], ["latency", "cpu"])


def test_layout_of_a_page_other_than_default__expect_only_its_own_rows() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.add(TimeSeriesChart("latency"))
    dashboard.add(TimeSeriesChart("errors"))

    dashboard.row("errors", page="requests")

    assert dashboard.layout("requests") == ([Row(["errors"])], [])


def test_layout_of_an_undeclared_page__expect_an_empty_layout() -> None:
    assert Dashboard(path=":memory:").layout("requests") == ([], [])


def test_widget_page_never_placed__expect_default() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.add(TimeSeriesChart("latency"))

    assert dashboard.widget_page("latency") == "default"


def test_widget_page_placed_by_row__expect_its_page() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.add(TimeSeriesChart("latency"))
    dashboard.row("latency", page="requests")

    assert dashboard.widget_page("latency") == "requests"


def test_module_level_page_and_row__expect_the_default_dashboard() -> None:
    dachshund.default(path=":memory:")
    dachshund.add(TimeSeriesChart("latency"))

    dachshund.page("requests", title="Requests")
    dachshund.row("latency", page="requests")

    dashboard = dachshund.default()
    assert dashboard.pages["requests"].title == "Requests"
    assert dashboard.layout("requests") == ([Row(["latency"])], [])


def test_add_on_a_page__expect_it_in_that_pages_flow() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.add(TimeSeriesChart("latency"))
    dashboard.add(TimeSeriesChart("errors"), page="requests")

    assert dashboard.layout() == ([], ["latency"])
    assert dashboard.layout("requests") == ([], ["errors"])
    assert "requests" in dashboard.pages


def test_row_naming_a_widget_on_another_page__expect_value_error() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.add(TimeSeriesChart("errors"), page="requests")

    with pytest.raises(ValueError, match="on another page: errors"):
        dashboard.row("errors")


def test_row_with_a_column__expect_rows_then_flow() -> None:
    dashboard = Dashboard(path=":memory:")
    latency = dashboard.add(TimeSeriesChart("latency"))
    errors = dashboard.add(TimeSeriesChart("errors"))
    cpu = dashboard.add(TimeSeriesChart("cpu"))
    dashboard.add(TimeSeriesChart("disk"))

    dashboard.row(latency, dashboard.column(errors, cpu))

    assert dashboard.layout() == (
        [Row(["latency", Column(["errors", "cpu"])])],
        ["disk"],
    )


def test_include__expect_pages_tabs_widgets_and_actions_registered() -> None:
    dashboard = Dashboard(path=":memory:")
    overview = Page("overview", title="Overview")
    latency = overview.add(TimeSeriesChart("latency"))
    errors = overview.add(TimeSeriesChart("errors"))
    overview.row(errors, latency)

    @overview.action("flush")
    def flush(ctx: dict) -> None: ...

    activity = Page("activity")
    commands = activity.tab("commands")
    commands.add(BarChart("on_command", x="name"))

    dashboard.include(overview)
    dashboard.include(activity)

    assert list(dashboard.pages) == ["overview", "activity", "activity/commands"]
    assert dashboard.layout("overview") == ([Row(["errors", "latency"])], [])
    assert dashboard.layout("activity/commands") == ([], ["on_command"])
    assert dashboard.widget_page("on_command") == "activity/commands"
    assert dashboard.actions["flush"].handler is flush
    assert overview.included and commands.included


def test_include_with_a_taken_name__expect_nothing_added() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.add(TimeSeriesChart("latency"))
    page = Page("overview")
    page.add(TimeSeriesChart("errors"))
    page.add(TimeSeriesChart("latency"))

    with pytest.raises(ValueError, match="already taken: latency"):
        dashboard.include(page)

    assert list(dashboard.widgets) == ["latency"]
    assert dashboard.pages == {}
    assert not page.included


def test_include_with_the_same_widget_in_two_tabs__expect_value_error() -> None:
    page = Page("activity")
    page.tab("a").add(TimeSeriesChart("latency"))
    page.tab("b").add(TimeSeriesChart("latency"))

    with pytest.raises(ValueError, match="already taken: latency"):
        Dashboard(path=":memory:").include(page)


def test_include_of_a_persisting_widget_without_storage__expect_nothing_added() -> None:
    dashboard = Dashboard(path=":memory:")
    page = Page("activity")
    page.add(TimeSeriesChart("latency"))
    page.add(BarChart("commands", x="name", persist=True))

    with pytest.raises(ValueError, match="no storage is configured"):
        dashboard.include(page)

    assert dashboard.widgets == {}


def test_include_of_a_tab__expect_value_error() -> None:
    tab = Page("activity").tab("commands")

    with pytest.raises(ValueError, match="is a tab"):
        Dashboard(path=":memory:").include(tab)


def test_include_twice__expect_the_second_ignored() -> None:
    dashboard = Dashboard(path=":memory:")
    page = Page("overview")
    page.add(TimeSeriesChart("latency"))
    dashboard.include(page)

    assert dashboard.include(page) is page
    assert list(dashboard.widgets) == ["latency"]


def test_include_of_another_page_with_a_taken_name__expect_value_error() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.include(Page("overview"))

    with pytest.raises(ValueError, match="already taken: overview"):
        dashboard.include(Page("overview"))


def test_include_of_one_page_in_two_dashboards__expect_both_to_hold_it() -> None:
    page = Page("overview")
    page.add(TimeSeriesChart("latency"))
    first, second = Dashboard(path=":memory:"), Dashboard(path=":memory:")

    first.include(page)
    second.include(page)

    assert first.pages["overview"] is second.pages["overview"] is page


def test_add_on_a_page_with_tabs__expect_value_error() -> None:
    dashboard = Dashboard(path=":memory:")
    page = Page("activity")
    page.tab("commands")
    dashboard.include(page)

    with pytest.raises(ValueError, match="has tabs"):
        dashboard.add(TimeSeriesChart("latency"), page="activity")


def test_module_level_add_and_include__expect_the_default_dashboard() -> None:
    dachshund.default(path=":memory:")
    page = dachshund.Page("overview")
    page.add(TimeSeriesChart("latency"))

    dachshund.include(page)
    dachshund.add(TimeSeriesChart("errors"), page="errors")

    dashboard = dachshund.default()
    assert dashboard.widget_page("latency") == "overview"
    assert dashboard.widget_page("errors") == "errors"


def test_row_on_a_page_with_tabs__expect_value_error() -> None:
    dashboard = Dashboard(path=":memory:")
    page = Page("activity")
    page.tab("commands")
    dashboard.include(page)
    dashboard.add(TimeSeriesChart("latency"))

    with pytest.raises(ValueError, match="has tabs"):
        dashboard.row("latency", page="activity")
