import asyncio
import json
import threading
from pathlib import Path
from typing import Any, Sequence

import pytest
from aiohttp.test_utils import TestClient, TestServer

from dachshund.registry import Dashboard
from dachshund.storage.events import Event
from dachshund.widgets.base import Widget
from dachshund.widgets.chart.timeseries import TimeSeriesChart
from dachshund.runtime.http import (
    FALLBACK_NAME,
    cards,
    create_app,
    create_environment,
    heading,
)

FIXTURE_SCRIPT = Path(__file__).parent / "fixtures" / "gauge.js"


@pytest.mark.asyncio
async def test_index__expect_the_dashboard_shell() -> None:
    async with TestClient(
        TestServer(create_app(Dashboard("Ada", path=":memory:")))
    ) as client:
        response = await client.get("/")
        body = await response.text()

    assert response.status == 200
    assert response.content_type == "text/html"
    assert "dachshund" in body


@pytest.mark.asyncio
async def test_index_with_a_description__expect_it_rendered() -> None:
    app = create_app(
        Dashboard("Ada", description="Code Society's Matrix bot", path=":memory:")
    )

    async with TestClient(TestServer(app)) as client:
        response = await client.get("/")
        body = await response.text()

    assert "<title>Ada</title>" in body
    assert "Code Society&#39;s Matrix bot" in body
    assert "just now" in body


@pytest.mark.asyncio
async def test_index_without_a_description__expect_no_description() -> None:
    async with TestClient(
        TestServer(create_app(Dashboard("Ada", path=":memory:")))
    ) as client:
        response = await client.get("/")
        body = await response.text()

    assert "service-description" not in body


@pytest.mark.asyncio
async def test_static__expect_the_asset_served() -> None:
    async with TestClient(
        TestServer(create_app(Dashboard("Ada", path=":memory:")))
    ) as client:
        response = await client.get("/_static/dashboard.css")
        body = await response.text()

    assert response.status == 200
    assert ".card" in body


@pytest.mark.asyncio
async def test_unknown_route__expect_not_found() -> None:
    async with TestClient(
        TestServer(create_app(Dashboard("Ada", path=":memory:")))
    ) as client:
        response = await client.get("/nope")

    assert response.status == 404


def test_environment_render__expect_escaped_values() -> None:
    template = create_environment().from_string("{{ value }}")

    assert template.render(value="<script>") == "&lt;script&gt;"


@pytest.mark.asyncio
async def test_index_without_a_name__expect_a_generic_title() -> None:
    async with TestClient(TestServer(create_app(Dashboard(path=":memory:")))) as client:
        response = await client.get("/")
        body = await response.text()

    assert f"<title>{FALLBACK_NAME}</title>" in body


@pytest.mark.asyncio
async def test_index__expect_the_client_bundle_loaded() -> None:
    async with TestClient(TestServer(create_app(Dashboard(path=":memory:")))) as client:
        response = await client.get("/")
        body = await response.text()

    assert '<script src="/_static/uplot.min.js"></script>' in body
    assert '<script src="/_static/dashboard.js"></script>' in body


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "asset", ["uplot.min.js", "uplot.min.css", "dashboard.js", "dashboard.css"]
)
async def test_static__expect_the_vendored_bundle_served(asset: str) -> None:
    async with TestClient(TestServer(create_app(Dashboard(path=":memory:")))) as client:
        response = await client.get(f"/_static/{asset}")

    assert response.status == 200


@pytest.mark.asyncio
async def test_index_with_a_widget__expect_its_points_hydrated() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.chart("latency", type="timeseries")
    dashboard.emit("latency", value=96)
    await dashboard.events.append(dashboard.drain())

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/")
        body = await response.text()

    assert 'data-widget="latency"' in body
    assert 'data-type="timeseries"' in body
    assert "96.0" in body


def test_heading__expect_the_title_when_given() -> None:
    chart = TimeSeriesChart("latency", source="latency", title="Response time")

    assert heading(chart) == "Response time"


def test_heading__expect_a_readable_name_without_a_title() -> None:
    assert heading(TimeSeriesChart("requests_per_sec", source="request")) == (
        "requests per sec"
    )


@pytest.mark.asyncio
async def test_index_with_a_titled_bar__expect_its_title_shown() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.chart("command_calls", type="bar", x="name", title="Calls Per Command")

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/")
        body = await response.text()

    assert "Calls Per Command" in body
    assert ">name<" not in body


@pytest.mark.asyncio
async def test_index_with_several_y_fields__expect_every_series_hydrated() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.chart("send_latency", type="timeseries", y=["p50", "p95"])
    dashboard.emit("send_latency", p50=10, p95=40)
    await dashboard.events.append(dashboard.drain())

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/")
        body = await response.text()

    assert "p50" in body
    assert "p95" in body


@pytest.mark.asyncio
async def test_cards__expect_a_series_aware_payload() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.chart("send_latency", type="timeseries", y=["p50", "p95"])

    payload = json.loads((await cards(dashboard))[0]["payload"])

    assert payload["series"] == ["p50", "p95"]
    assert payload["y"] == [[], []]


@pytest.mark.asyncio
async def test_index_with_an_unreadable_value__expect_the_page_to_survive() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.chart("latency", type="timeseries")
    dashboard.emit("latency", value="fast")
    dashboard.emit("latency", value=float("inf"))
    dashboard.emit("latency", value=96)
    await dashboard.events.append(dashboard.drain())

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/")
        body = await response.text()

    assert response.status == 200
    assert "NaN" not in body
    assert "Infinity" not in body


@pytest.mark.asyncio
async def test_index_without_custom_widgets__expect_no_widget_asset_tags() -> None:
    async with TestClient(
        TestServer(create_app(Dashboard("Ada", path=":memory:")))
    ) as client:
        response = await client.get("/")
        body = await response.text()

    assert "/_static/widgets/" not in body


@pytest.mark.asyncio
async def test_index_with_a_custom_widget__expect_its_script_before_dashboard_js() -> (
    None
):
    class Gauge(Widget):
        type = "custom_test_http_gauge"
        script = FIXTURE_SCRIPT

        def render(self, events: Sequence[Event]) -> dict[str, Any]:
            return {}

        def update(self, event: Event) -> dict[str, Any] | None:
            return None

    dashboard = Dashboard(path=":memory:")
    dashboard.add(Gauge("cpu", source="cpu"))

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/")
        body = await response.text()

    script_tag = '<script src="/_static/widgets/custom_test_http_gauge.js"></script>'

    assert script_tag in body
    assert body.index(script_tag) < body.index(
        '<script src="/_static/dashboard.js"></script>'
    )


@pytest.mark.asyncio
async def test_index_with_two_instances_of_a_custom_type__expect_one_script_tag() -> (
    None
):
    class Meter(Widget):
        type = "custom_test_http_meter"
        script = FIXTURE_SCRIPT

        def render(self, events: Sequence[Event]) -> dict[str, Any]:
            return {}

        def update(self, event: Event) -> dict[str, Any] | None:
            return None

    dashboard = Dashboard(path=":memory:")
    dashboard.add(Meter("cpu", source="cpu"))
    dashboard.add(Meter("memory", source="memory"))

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/")
        body = await response.text()

    assert body.count("/_static/widgets/custom_test_http_meter.js") == 1


@pytest.mark.asyncio
async def test_index_with_the_builtin_charts__expect_one_shared_asset_pair() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.chart("latency", type="timeseries")
    dashboard.chart("throughput", type="line", x="requests")
    dashboard.chart("errors", type="bar", x="code")

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/")
        body = await response.text()

    types = ("timeseries", "line", "bar")

    assert body.count("/_static/widgets/") == 2  # one script tag, one style tag
    assert sum(body.count(f"/_static/widgets/{t}.js") for t in types) == 1
    assert sum(body.count(f"/_static/widgets/{t}.css") for t in types) == 1


@pytest.mark.asyncio
async def test_widget_script__expect_the_file_served() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.chart("latency", type="timeseries")

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/_static/widgets/timeseries.js")
        body = await response.text()

    assert response.status == 200
    assert "Dachshund.widget" in body


@pytest.mark.asyncio
async def test_widget_style__expect_the_file_served() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.chart("latency", type="timeseries")

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/_static/widgets/timeseries.css")
        body = await response.text()

    assert response.status == 200
    assert "chart-tooltip" in body


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["value.js", "value.css", "nope.js", "nope.css"])
async def test_widget_asset_without_one_declared__expect_not_found(path: str) -> None:
    # "value" isn't a registered widget type at all, and no built-in type is
    # named "nope" either. Both should 404, not error.
    async with TestClient(
        TestServer(create_app(Dashboard("Ada", path=":memory:")))
    ) as client:
        response = await client.get(f"/_static/widgets/{path}")

    assert response.status == 404


@pytest.mark.asyncio
async def test_cards_with_a_table__expect_each_row_carrying_resolved_actions() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("ban", label="Ban", confirm=True)(lambda ctx, user: None)
    dashboard.widget("sessions", type="table", columns=["user"], actions=["ban"])
    dashboard.emit("sessions", user="ada")
    await dashboard.events.append(dashboard.drain())

    card = (await cards(dashboard))[0]
    payload = json.loads(card["payload"])

    assert card["actions"] == []
    assert payload["rows"][0]["actions"] == [
        {"name": "ban", "label": "Ban", "confirm": True, "args": {}}
    ]


@pytest.mark.asyncio
async def test_cards_with_a_table_and_an_unregistered_action__expect_a_sensible_fallback() -> (
    None
):
    dashboard = Dashboard(path=":memory:")
    dashboard.widget("sessions", type="table", columns=["user"], actions=["nope"])
    dashboard.emit("sessions", user="ada")
    await dashboard.events.append(dashboard.drain())

    payload = json.loads((await cards(dashboard))[0]["payload"])

    assert payload["rows"][0]["actions"] == [
        {"name": "nope", "label": "nope", "confirm": False, "args": {}}
    ]


@pytest.mark.asyncio
async def test_index_with_a_table__expect_no_card_level_action_row() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("ban", label="Ban", confirm=True)(lambda ctx, user: None)
    dashboard.widget("sessions", type="table", columns=["user"], actions=["ban"])

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/")
        body = await response.text()

    assert "card-actions" not in body


@pytest.mark.asyncio
async def test_index_with_a_button__expect_the_card_level_action_row() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("ping", label="Ping")(lambda ctx: None)
    dashboard.widget("ping", type="button", actions=["ping"])

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/")
        body = await response.text()

    assert "card-actions" in body
    assert 'data-action="ping"' in body


@pytest.mark.asyncio
async def test_cards_with_action_args__expect_them_on_the_card_level_action() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("block_user")(lambda ctx, user_id: None)
    dashboard.widget(
        "last_signup",
        type="button",
        actions=["block_user"],
        action_args={"block_user": {"user_id": "42"}},
    )

    card = (await cards(dashboard))[0]

    assert card["actions"] == [
        {"name": "block_user", "label": "block_user", "confirm": False, "args": {"user_id": "42"}}
    ]


@pytest.mark.asyncio
async def test_index_with_action_args__expect_them_rendered_as_data_args() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("block_user")(lambda ctx, user_id: None)
    dashboard.widget(
        "last_signup",
        type="button",
        actions=["block_user"],
        action_args={"block_user": {"user_id": "42"}},
    )

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/")
        body = await response.text()

    assert 'data-args="{&#34;user_id&#34;: &#34;42&#34;}"' in body


@pytest.mark.asyncio
async def test_widget_asset_for_a_type_without_one__expect_not_found() -> None:
    class Plain(Widget):
        type = "custom_test_http_plain"

    dashboard = Dashboard(path=":memory:")
    dashboard.add(Plain("cpu", source="cpu"))

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/_static/widgets/custom_test_http_plain.js")

    assert response.status == 404


@pytest.mark.asyncio
async def test_widget_page__expect_the_first_page_with_a_next_cursor() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.widget("sessions", type="table", columns=["user"], key="user")
    for i in range(6):
        dashboard.emit("sessions", user=f"user{i}")
    await dashboard.events.append(dashboard.drain())

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/_widgets/sessions/page")
        payload = await response.json()

    assert response.status == 200
    assert len(payload["rows"]) == 5
    assert payload["next_cursor"] == "user4"


@pytest.mark.asyncio
async def test_widget_page_with_a_cursor__expect_the_slice_after_it_with_resolved_actions() -> (
    None
):
    dashboard = Dashboard(path=":memory:")
    dashboard.action("ban", label="Ban", confirm=True)(lambda ctx, user: None)
    dashboard.widget(
        "sessions", type="table", columns=["user"], key="user", actions=["ban"]
    )
    for i in range(6):
        dashboard.emit("sessions", user=f"user{i}")
    await dashboard.events.append(dashboard.drain())

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/_widgets/sessions/page?cursor=user4")
        payload = await response.json()

    assert response.status == 200
    assert payload["next_cursor"] is None
    assert len(payload["rows"]) == 1
    assert payload["rows"][0]["actions"] == [
        {"name": "ban", "label": "Ban", "confirm": True, "args": {}}
    ]


@pytest.mark.asyncio
async def test_widget_page_with_a_stale_cursor__expect_it_restarted() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.widget("sessions", type="table", columns=["user"], key="user")
    dashboard.emit("sessions", user="ada")
    await dashboard.events.append(dashboard.drain())

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/_widgets/sessions/page?cursor=nope")
        payload = await response.json()

    assert [row["fields"]["user"] for row in payload["rows"]] == ["ada"]


@pytest.mark.asyncio
async def test_widget_page_with_a_loader__expect_its_rows_and_host_loop() -> None:
    host_loop = asyncio.new_event_loop()
    thread = threading.Thread(target=host_loop.run_forever, daemon=True)
    thread.start()

    seen_loop = None
    seen_ctx = None

    async def load(ctx, cursor: str | None, page_size: int) -> tuple[list[dict], str | None]:
        nonlocal seen_loop, seen_ctx
        seen_loop = asyncio.get_running_loop()
        seen_ctx = ctx
        return [{"user": "ada"}], None

    dashboard = Dashboard(path=":memory:", context={"bot": "b"})
    dashboard.widget("sessions", type="table", columns=["user"], loader=load)
    dashboard.host_loop = host_loop

    try:
        async with TestClient(TestServer(create_app(dashboard))) as client:
            response = await client.get("/_widgets/sessions/page")
            payload = await response.json()
    finally:
        host_loop.call_soon_threadsafe(host_loop.stop)
        thread.join(5)

    assert payload["rows"][0]["fields"] == {"user": "ada"}
    assert seen_loop is host_loop
    assert seen_ctx == {"bot": "b"}


@pytest.mark.asyncio
async def test_widget_page_of_an_unknown_widget__expect_not_found() -> None:
    async with TestClient(
        TestServer(create_app(Dashboard(path=":memory:")))
    ) as client:
        response = await client.get("/_widgets/nope/page")

    assert response.status == 404


@pytest.mark.asyncio
async def test_widget_page_of_a_non_paginated_widget__expect_not_found() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.chart("commands", type="bar", x="name")

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/_widgets/commands/page")

    assert response.status == 404


@pytest.mark.asyncio
async def test_index_with_a_table__expect_only_one_page_embedded() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.widget("sessions", type="table", columns=["user"], key="user")
    for i in range(6):
        dashboard.emit("sessions", user=f"user{i}")
    await dashboard.events.append(dashboard.drain())

    card = (await cards(dashboard))[0]
    payload = json.loads(card["payload"])

    assert len(payload["rows"]) == 5
    assert payload["next_cursor"] == "user4"
