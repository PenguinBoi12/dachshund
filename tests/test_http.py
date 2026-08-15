import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from dachshund.registry import Dashboard
from dachshund.widgets.chart.timeseries import TimeSeriesChart
from dachshund.runtime.http import (
    FALLBACK_NAME,
    cards,
    create_app,
    create_environment,
    heading,
)


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
