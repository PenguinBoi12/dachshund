import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, ClassVar

import pytest
from aiohttp.test_utils import TestClient, TestServer

from dachshund import BarChart, LineChart, Table, TimeSeriesChart
from dachshund.layout import Page
from dachshund.registry import Dashboard
from dachshund.runtime.http import create_app
from dachshund.runtime.keys import CLIENTS
from dachshund.runtime.ws import (
    PUMP_INTERVAL,
    WS_PATH,
    broadcast,
    hydrate,
    pump,
    updates,
)
from dachshund.storage.events import Event
from dachshund.widgets.persistable import PersistableWidget

RECEIVE_TIMEOUT = 5.0


@dataclass
class AppendingCounter(PersistableWidget):
    """A minimal op="append" widget that persists, for exercising the write
    path a persisting BarChart (op="replace") never touches."""

    total: float = field(default=0.0, init=False, repr=False, compare=False)

    type: ClassVar[str] = "test_appending_counter"
    op: ClassVar[str] = "append"

    def accumulate(self, event: Event) -> None:
        self.total += 1

    def snapshot(self) -> dict[str, Any]:
        return {"total": self.total}

    def restore(self, data: dict[str, Any]) -> None:
        self.total = data.get("total", 0.0)

    def update(self, event: Event) -> dict[str, Any] | None:
        return {"total": self.total}

    def render(self, events: object) -> dict[str, Any]:
        return {"total": self.total}


class FakeStorage:
    """An in-memory `Storage`, for tests that don't need real SQLite."""

    def __init__(self) -> None:
        self.saved: dict[str, dict[str, object]] = {}

    async def save(self, key: str, value: dict[str, object]) -> None:
        self.saved[key] = value

    async def load(self, key: str) -> dict[str, object] | None:
        return self.saved.get(key)


class PartiallyFlakyStorage:
    """A `Storage` that raises for one specific key, works normally for
    everything else, for testing that a failure stays isolated."""

    def __init__(self, fails_on: str) -> None:
        self.fails_on = fails_on
        self.saved: dict[str, dict[str, object]] = {}

    async def save(self, key: str, value: dict[str, object]) -> None:
        if key == self.fails_on:
            raise RuntimeError("boom")

        self.saved[key] = value

    async def load(self, key: str) -> dict[str, object] | None:
        if key == self.fails_on:
            raise RuntimeError("boom")

        return self.saved.get(key)


@pytest.mark.asyncio
async def test_updates__expect_one_per_widget_watching_the_source() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.row(TimeSeriesChart("latency"))
    dashboard.row(TimeSeriesChart("also_latency", source="latency"))
    dashboard.row(TimeSeriesChart("errors"))

    messages = await updates(dashboard, [Event("latency", {"value": 96})])

    assert [message["widget"] for message in messages] == ["latency", "also_latency"]
    assert messages[0]["op"] == "append"
    assert messages[0]["data"]["y"] == [96.0]


@pytest.mark.asyncio
async def test_updates_of_an_unwatched_source__expect_nothing() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.row(TimeSeriesChart("latency"))

    assert await updates(dashboard, [Event("errors")]) == []


@pytest.mark.asyncio
async def test_emit_while_connected__expect_the_update_pushed() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.row(TimeSeriesChart("latency"))

    async with TestClient(TestServer(create_app(dashboard))) as client:
        async with client.ws_connect(WS_PATH) as page:
            dashboard.emit("latency", value=96)
            messages = await page.receive_json(timeout=RECEIVE_TIMEOUT)

    assert messages == [
        {
            "widget": "latency",
            "op": "append",
            "data": {"x": messages[0]["data"]["x"], "y": [96.0]},
        }
    ]


@pytest.mark.asyncio
async def test_emit_while_two_pages_are_open__expect_both_told() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.row(TimeSeriesChart("latency"))

    async with TestClient(TestServer(create_app(dashboard))) as client:
        async with client.ws_connect(WS_PATH) as one:
            async with client.ws_connect(WS_PATH) as two:
                dashboard.emit("latency", value=96)

                first = await one.receive_json(timeout=RECEIVE_TIMEOUT)
                second = await two.receive_json(timeout=RECEIVE_TIMEOUT)

    assert first == second


@pytest.mark.asyncio
async def test_connect__expect_the_page_tracked_then_forgotten() -> None:
    app = create_app(Dashboard(path=":memory:"))

    async with TestClient(TestServer(app)) as client:
        async with client.ws_connect(WS_PATH):
            assert len(app[CLIENTS]) == 1

        await client.get("/")  # Let the handler finish tidying up.

    assert app[CLIENTS] == {}


@pytest.mark.asyncio
async def test_emit_of_a_batch__expect_one_message_carrying_them_all() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.row(TimeSeriesChart("latency"))

    async with TestClient(TestServer(create_app(dashboard))) as client:
        async with client.ws_connect(WS_PATH) as page:
            for value in (96, 108, 120):
                dashboard.emit("latency", value=value)

            messages = await page.receive_json(timeout=RECEIVE_TIMEOUT)

    assert [message["data"]["y"] for message in messages] == [[96.0], [108.0], [120.0]]


class Gone:
    """A page that has already gone away."""

    async def send_json(self, message: object) -> None:
        raise ConnectionResetError


@pytest.mark.asyncio
async def test_broadcast_to_a_page_that_went_away__expect_it_dropped() -> None:
    app = create_app(Dashboard(path=":memory:"))
    gone = Gone()
    app[CLIENTS][gone] = None  # type: ignore[index]

    await broadcast(app, [{"widget": "latency", "op": "append", "data": {}}])

    assert app[CLIENTS] == {}


@pytest.mark.asyncio
async def test_broadcast_of_nothing__expect_no_send() -> None:
    app = create_app(Dashboard(path=":memory:"))
    app[CLIENTS][Gone()] = None  # type: ignore[index]

    await broadcast(app, [])

    assert len(app[CLIENTS]) == 1


@pytest.mark.asyncio
async def test_updates_of_a_replacing_widget__expect_one_rebuild_per_batch() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.row(BarChart("commands", x="name"))

    for name in ("/ban", "/help", "/ban"):
        dashboard.emit("commands", name=name, value=1)

    events = dashboard.drain()
    await dashboard.events.append(events)
    messages = await updates(dashboard, events)

    assert len(messages) == 1
    assert messages[0] == {
        "widget": "commands",
        "op": "replace",
        "data": {
            "series": ["value"],
            "x": ["/ban", "/help"],
            "y": [[2.0, 1.0]],
        },
    }


@pytest.mark.asyncio
async def test_updates_of_mixed_widgets__expect_each_kind_handled() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.row(TimeSeriesChart("latency"))
    dashboard.row(BarChart("bars", source="latency", x="name"))

    dashboard.emit("latency", value=96, name="a")
    dashboard.emit("latency", value=108, name="a")

    events = dashboard.drain()
    await dashboard.events.append(events)
    messages = await updates(dashboard, events)

    assert [message["op"] for message in messages] == [
        "append",
        "append",
        "replace",
    ]


@pytest.mark.asyncio
async def test_updates_with_an_unreadable_x__expect_the_point_dropped() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.row(LineChart("perf", x="requests", y="ms"))

    dashboard.emit("perf", requests="many", ms=96)
    dashboard.emit("perf", requests=120, ms=108)

    events = dashboard.drain()
    await dashboard.events.append(events)
    messages = await updates(dashboard, events)

    assert [message["data"]["x"] for message in messages] == [120.0]


@pytest.mark.asyncio
async def test_updates_with_a_bad_event__expect_the_other_widgets_unaffected() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.row(TimeSeriesChart("latency"))
    dashboard.row(TimeSeriesChart("also_latency", source="latency"))

    dashboard.emit("latency", value="fast")

    events = dashboard.drain()
    await dashboard.events.append(events)
    messages = await updates(dashboard, events)

    assert [message["widget"] for message in messages] == ["latency", "also_latency"]
    assert [message["data"]["y"] for message in messages] == [[None], [None]]


@pytest.mark.asyncio
async def test_hydrate_without_storage__expect_no_error() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.row(TimeSeriesChart("latency"))

    await hydrate(dashboard)


@pytest.mark.asyncio
async def test_hydrate__expect_a_persisting_widget_seeded_from_storage() -> None:
    storage = FakeStorage()
    dashboard = Dashboard(path=":memory:", storage=storage)  # type: ignore[arg-type]
    dashboard.row(BarChart("commands", x="name", persist=True))
    dashboard.row(TimeSeriesChart("latency"))
    await storage.save("commands", {"entries": {"/ban": 3}, "seen_at": {}})

    await hydrate(dashboard)

    assert dashboard.widgets["commands"].state.entries == {"/ban": 3}  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_hydrate_called_again_with_the_same_set__expect_it_left_alone() -> None:
    storage = FakeStorage()
    dashboard = Dashboard(path=":memory:", storage=storage)  # type: ignore[arg-type]
    dashboard.row(BarChart("commands", x="name", persist=True))
    await storage.save("commands", {"entries": {"/ban": 3}, "seen_at": {}})

    hydrated: set[str] = set()
    await hydrate(dashboard, hydrated)

    # Storage changes after the fact (e.g. a fresh snapshot from a live
    # update); an already-hydrated widget must not be reloaded over it.
    await storage.save("commands", {"entries": {"/mute": 9}, "seen_at": {}})
    await hydrate(dashboard, hydrated)

    assert dashboard.widgets["commands"].state.entries == {"/ban": 3}  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_hydrate_of_a_widget_registered_since_the_last_call__expect_it_seeded() -> (
    None
):
    storage = FakeStorage()
    dashboard = Dashboard(path=":memory:", storage=storage)  # type: ignore[arg-type]
    dashboard.row(BarChart("commands", x="name", persist=True))
    await storage.save("commands", {"entries": {"/ban": 3}, "seen_at": {}})

    hydrated: set[str] = set()
    await hydrate(dashboard, hydrated)

    dashboard.row(BarChart("errors", x="kind", persist=True))
    await storage.save("errors", {"entries": {"timeout": 2}, "seen_at": {}})
    await hydrate(dashboard, hydrated)

    assert dashboard.widgets["errors"].state.entries == {"timeout": 2}  # type: ignore[attr-defined]
    assert dashboard.widgets["commands"].state.entries == {"/ban": 3}  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_hydrate_when_storage_raises__expect_it_retried_on_the_next_call(
    caplog: pytest.LogCaptureFixture,
) -> None:
    storage = PartiallyFlakyStorage(fails_on="commands")
    dashboard = Dashboard(path=":memory:", storage=storage)  # type: ignore[arg-type]
    dashboard.row(BarChart("commands", x="name", persist=True))

    hydrated: set[str] = set()

    with caplog.at_level(logging.ERROR, logger="dachshund"):
        await hydrate(dashboard, hydrated)

    assert "commands" not in hydrated

    storage.fails_on = ""
    await storage.save("commands", {"entries": {"/ban": 3}, "seen_at": {}})
    await hydrate(dashboard, hydrated)

    assert dashboard.widgets["commands"].state.entries == {"/ban": 3}  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_updates_of_a_persisting_widget__expect_it_saved() -> None:
    storage = FakeStorage()
    dashboard = Dashboard(path=":memory:", storage=storage)  # type: ignore[arg-type]
    dashboard.row(BarChart("commands", x="name", persist=True))

    dashboard.emit("commands", name="/ban", value=1)
    events = dashboard.drain()
    await dashboard.events.append(events)
    await updates(dashboard, events)

    assert storage.saved["commands"]["entries"] == {"/ban": 1.0}


@pytest.mark.asyncio
async def test_updates_of_a_persisting_table__expect_it_saved() -> None:
    storage = FakeStorage()
    dashboard = Dashboard(path=":memory:", storage=storage)  # type: ignore[arg-type]
    dashboard.row(Table("sessions", columns=["user"], key="user", persist=True))

    dashboard.emit("sessions", user="ada")
    events = dashboard.drain()
    await dashboard.events.append(events)
    await updates(dashboard, events)

    assert storage.saved["sessions"]["entries"] == {"ada": {"user": "ada"}}


@pytest.mark.asyncio
async def test_updates_of_an_untouched_widget__expect_nothing_saved() -> None:
    storage = FakeStorage()
    dashboard = Dashboard(path=":memory:", storage=storage)  # type: ignore[arg-type]
    dashboard.row(BarChart("commands", x="name", persist=True))
    dashboard.row(BarChart("errors", x="kind", persist=True))

    dashboard.emit("commands", name="/ban", value=1)
    events = dashboard.drain()
    await dashboard.events.append(events)
    await updates(dashboard, events)

    assert "errors" not in storage.saved


@pytest.mark.asyncio
async def test_updates_with_a_persisting_and_a_plain_bar__expect_only_the_persisting_one_saved() -> (
    None
):
    storage = FakeStorage()
    dashboard = Dashboard(path=":memory:", storage=storage)  # type: ignore[arg-type]
    dashboard.row(BarChart("commands", x="name", source="calls", persist=True))
    dashboard.row(BarChart("recent", x="name", source="calls"))

    dashboard.emit("calls", name="/ban", value=1)
    events = dashboard.drain()
    await dashboard.events.append(events)
    messages = await updates(dashboard, events)

    assert "commands" in storage.saved
    assert "recent" not in storage.saved
    assert {message["widget"] for message in messages} == {"commands", "recent"}


@pytest.mark.asyncio
async def test_updates_of_a_plain_bar__expect_nothing_accumulated() -> None:
    dashboard = Dashboard(path=":memory:")
    chart = BarChart("commands", x="name")
    dashboard.row(chart)

    dashboard.emit("commands", name="/ban", value=1)
    events = dashboard.drain()
    await dashboard.events.append(events)
    await updates(dashboard, events)

    assert chart.state.entries == {}  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_updates_of_a_persisting_append_widget__expect_it_saved() -> None:
    storage = FakeStorage()
    dashboard = Dashboard(path=":memory:", storage=storage)  # type: ignore[arg-type]
    dashboard.row(AppendingCounter("hits", source="hits", persist=True))

    dashboard.emit("hits", value=1)
    events = dashboard.drain()
    await dashboard.events.append(events)
    messages = await updates(dashboard, events)

    assert storage.saved["hits"] == {"total": 1.0}
    assert messages == [{"widget": "hits", "op": "append", "data": {"total": 1.0}}]


@pytest.mark.asyncio
async def test_hydrate_when_storage_raises__expect_the_other_widgets_still_seeded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    storage = PartiallyFlakyStorage(fails_on="broken")
    dashboard = Dashboard(path=":memory:", storage=storage)  # type: ignore[arg-type]
    dashboard.row(BarChart("broken", x="name", persist=True))
    dashboard.row(BarChart("commands", x="name", persist=True))
    await storage.save("commands", {"entries": {"/ban": 3}, "seen_at": {}})

    with caplog.at_level(logging.ERROR, logger="dachshund"):
        await hydrate(dashboard)

    assert dashboard.widgets["commands"].state.entries == {"/ban": 3}  # type: ignore[attr-defined]
    assert dashboard.widgets["broken"].state.entries == {}  # type: ignore[attr-defined]
    assert "'broken'" in caplog.text


@pytest.mark.asyncio
async def test_updates_of_a_paginated_widget__expect_a_content_free_ping() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.row(Table("sessions", columns=["user"]))

    dashboard.emit("sessions", user="ada")
    events = dashboard.drain()
    await dashboard.events.append(events)
    messages = await updates(dashboard, events)

    assert messages == [{"widget": "sessions", "op": "replace", "data": {}}]


@pytest.mark.asyncio
async def test_updates_of_a_paginated_widget__expect_events_not_reread() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.row(Table("sessions", columns=["user"]))

    dashboard.emit("sessions", user="ada")
    events = dashboard.drain()
    await dashboard.events.append(events)

    async def fail(source: str) -> list[Event]:
        raise AssertionError("a paginated widget shouldn't need its events reread")

    dashboard.events.events = fail  # type: ignore[method-assign]

    await updates(dashboard, events)


@pytest.mark.asyncio
async def test_updates_of_a_non_paginated_replace_widget__expect_it_unaffected() -> (
    None
):
    dashboard = Dashboard(path=":memory:")
    dashboard.row(BarChart("commands", x="name"))

    dashboard.emit("commands", name="/ban", value=1)
    events = dashboard.drain()
    await dashboard.events.append(events)
    messages = await updates(dashboard, events)

    assert messages[0]["data"]["x"] == ["/ban"]


@pytest.mark.asyncio
async def test_pump__expect_the_skip_set_built_from_non_rollup_safe_widgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.row(Table("sessions", columns=["user"]))
    dashboard.row(TimeSeriesChart("latency"))
    app = create_app(dashboard)

    calls = []

    async def fake_compact(skip_rollup: frozenset[str] = frozenset()) -> None:
        calls.append(skip_rollup)

    monkeypatch.setattr(dashboard.events, "compact", fake_compact)

    task = asyncio.create_task(pump(app))
    await asyncio.sleep(PUMP_INTERVAL * 2)
    task.cancel()

    with suppress(asyncio.CancelledError):
        await task

    assert calls
    assert "sessions" in calls[0]
    assert "latency" not in calls[0]


@pytest.mark.asyncio
async def test_updates_when_storage_raises_for_one_widget__expect_the_others_unaffected(
    caplog: pytest.LogCaptureFixture,
) -> None:
    storage = PartiallyFlakyStorage(fails_on="broken")
    dashboard = Dashboard(path=":memory:", storage=storage)  # type: ignore[arg-type]
    dashboard.row(BarChart("broken", x="name", persist=True))
    dashboard.row(BarChart("commands", x="name", persist=True))

    dashboard.emit("broken", name="/x", value=1)
    dashboard.emit("commands", name="/ban", value=1)
    events = dashboard.drain()
    await dashboard.events.append(events)

    with caplog.at_level(logging.ERROR, logger="dachshund"):
        messages = await updates(dashboard, events)

    assert storage.saved["commands"]["entries"] == {"/ban": 1.0}
    assert "broken" not in storage.saved
    assert {message["widget"] for message in messages} == {"broken", "commands"}
    assert "'broken'" in caplog.text


class Recording:
    """A page that keeps every batch it is sent."""

    def __init__(self) -> None:
        self.sent: list[object] = []

    async def send_json(self, message: object) -> None:
        self.sent.append(message)


@pytest.mark.asyncio
async def test_broadcast_to_pages__expect_each_told_only_its_widgets() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.row(TimeSeriesChart("latency"))
    dashboard.row(TimeSeriesChart("errors"), page="requests")
    app = create_app(dashboard)

    overview, requests, everything = Recording(), Recording(), Recording()
    app[CLIENTS][overview] = "default"  # type: ignore[index]
    app[CLIENTS][requests] = "requests"  # type: ignore[index]
    app[CLIENTS][everything] = None  # type: ignore[index]

    latency = {"widget": "latency", "op": "append", "data": {}}
    errors = {"widget": "errors", "op": "append", "data": {}}
    await broadcast(app, [latency, errors])

    assert overview.sent == [[latency]]
    assert requests.sent == [[errors]]
    assert everything.sent == [[latency, errors]]


@pytest.mark.asyncio
async def test_broadcast_with_nothing_for_a_page__expect_no_send() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.row(TimeSeriesChart("latency"))
    dashboard.page("requests")
    app = create_app(dashboard)

    requests = Recording()
    app[CLIENTS][requests] = "requests"  # type: ignore[index]

    await broadcast(app, [{"widget": "latency", "op": "append", "data": {}}])

    assert requests.sent == []


@pytest.mark.asyncio
async def test_connect_with_a_page__expect_it_remembered() -> None:
    app = create_app(Dashboard(path=":memory:"))

    async with TestClient(TestServer(app)) as client:
        async with client.ws_connect(f"{WS_PATH}?page=requests"):
            assert list(app[CLIENTS].values()) == ["requests"]


@pytest.mark.asyncio
async def test_emit_while_on_another_page__expect_nothing_pushed() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.row(TimeSeriesChart("latency"))
    dashboard.row(TimeSeriesChart("errors"), page="requests")

    async with TestClient(TestServer(create_app(dashboard))) as client:
        async with client.ws_connect(f"{WS_PATH}?page=requests") as page:
            dashboard.emit("latency", value=96)
            dashboard.emit("errors", value=1)
            messages = await page.receive_json(timeout=RECEIVE_TIMEOUT)

    assert [message["widget"] for message in messages] == ["errors"]


@pytest.mark.asyncio
async def test_broadcast_to_a_tab__expect_only_its_widgets() -> None:
    dashboard = Dashboard(path=":memory:")
    activity = Page("activity")
    activity.tab("commands").row(TimeSeriesChart("calls"))
    activity.tab("errors").row(TimeSeriesChart("failures"))
    dashboard.include(activity)
    app = create_app(dashboard)

    commands = Recording()
    app[CLIENTS][commands] = "activity/commands"  # type: ignore[index]

    calls = {"widget": "calls", "op": "append", "data": {}}
    failures = {"widget": "failures", "op": "append", "data": {}}
    await broadcast(app, [calls, failures])

    assert commands.sent == [[calls]]
