import pytest
from aiohttp.test_utils import TestClient, TestServer

from dachshund.registry import Dashboard
from dachshund.runtime.http import create_app
from dachshund.runtime.keys import CLIENTS
from dachshund.runtime.ws import WS_PATH, broadcast, updates
from dachshund.storage.events import Event

RECEIVE_TIMEOUT = 5.0


def test_updates__expect_one_per_widget_watching_the_source() -> None:
    dashboard = Dashboard()
    dashboard.chart("latency", type="timeseries")
    dashboard.chart("also_latency", type="timeseries", source="latency")
    dashboard.chart("errors", type="timeseries")

    messages = updates(dashboard, [Event("latency", {"value": 96})])

    assert [message["widget"] for message in messages] == ["latency", "also_latency"]
    assert messages[0]["op"] == "append"
    assert messages[0]["data"]["y"] == [96.0]


def test_updates_of_an_unwatched_source__expect_nothing() -> None:
    dashboard = Dashboard()
    dashboard.chart("latency", type="timeseries")

    assert updates(dashboard, [Event("errors")]) == []


@pytest.mark.asyncio
async def test_emit_while_connected__expect_the_update_pushed() -> None:
    dashboard = Dashboard()
    dashboard.chart("latency", type="timeseries")

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
    dashboard = Dashboard()
    dashboard.chart("latency", type="timeseries")

    async with TestClient(TestServer(create_app(dashboard))) as client:
        async with client.ws_connect(WS_PATH) as one:
            async with client.ws_connect(WS_PATH) as two:
                dashboard.emit("latency", value=96)

                first = await one.receive_json(timeout=RECEIVE_TIMEOUT)
                second = await two.receive_json(timeout=RECEIVE_TIMEOUT)

    assert first == second


@pytest.mark.asyncio
async def test_connect__expect_the_page_tracked_then_forgotten() -> None:
    app = create_app(Dashboard())

    async with TestClient(TestServer(app)) as client:
        async with client.ws_connect(WS_PATH):
            assert len(app[CLIENTS]) == 1

        await client.get("/")  # Let the handler finish tidying up.

    assert app[CLIENTS] == set()


@pytest.mark.asyncio
async def test_emit_of_a_batch__expect_one_message_carrying_them_all() -> None:
    dashboard = Dashboard()
    dashboard.chart("latency", type="timeseries")

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
    app = create_app(Dashboard())
    gone = Gone()
    app[CLIENTS].add(gone)  # type: ignore[arg-type]

    await broadcast(app, [{"widget": "latency", "op": "append", "data": {}}])

    assert app[CLIENTS] == set()


@pytest.mark.asyncio
async def test_broadcast_of_nothing__expect_no_send() -> None:
    app = create_app(Dashboard())
    app[CLIENTS].add(Gone())  # type: ignore[arg-type]

    await broadcast(app, [])

    assert len(app[CLIENTS]) == 1


def test_updates_of_a_replacing_widget__expect_one_rebuild_per_batch() -> None:
    dashboard = Dashboard()
    dashboard.chart("commands", type="bar", x="name")

    for name in ("/ban", "/help", "/ban"):
        dashboard.emit("commands", name=name, value=1)

    events = dashboard.drain()
    messages = updates(dashboard, events)

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


def test_updates_of_mixed_widgets__expect_each_kind_handled() -> None:
    dashboard = Dashboard()
    dashboard.chart("latency", type="timeseries")
    dashboard.chart("bars", type="bar", source="latency", x="name")

    dashboard.emit("latency", value=96, name="a")
    dashboard.emit("latency", value=108, name="a")

    messages = updates(dashboard, dashboard.drain())

    assert [message["op"] for message in messages] == [
        "append",
        "append",
        "replace",
    ]


def test_updates_with_an_unreadable_x__expect_the_point_dropped() -> None:
    dashboard = Dashboard()
    dashboard.chart("perf", type="line", x="requests", y="ms")

    dashboard.emit("perf", requests="many", ms=96)
    dashboard.emit("perf", requests=120, ms=108)

    messages = updates(dashboard, dashboard.drain())

    assert [message["data"]["x"] for message in messages] == [120.0]


def test_updates_with_a_bad_event__expect_the_other_widgets_unaffected() -> None:
    dashboard = Dashboard()
    dashboard.chart("latency", type="timeseries")
    dashboard.chart("also_latency", type="timeseries", source="latency")

    dashboard.emit("latency", value="fast")

    messages = updates(dashboard, dashboard.drain())

    assert [message["widget"] for message in messages] == ["latency", "also_latency"]
    assert [message["data"]["y"] for message in messages] == [[None], [None]]
