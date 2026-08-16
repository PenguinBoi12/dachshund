import json
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
async def test_widget_asset_for_a_type_without_one__expect_not_found() -> None:
    class Plain(Widget):
        type = "custom_test_http_plain"

    dashboard = Dashboard(path=":memory:")
    dashboard.add(Plain("cpu", source="cpu"))

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/_static/widgets/custom_test_http_plain.js")

    assert response.status == 404
