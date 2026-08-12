import pytest
from aiohttp.test_utils import TestClient, TestServer

from dachshund.registry import Dashboard
from dachshund.runtime.http import FALLBACK_NAME, create_app, create_environment


@pytest.mark.asyncio
async def test_index__expect_the_dashboard_shell() -> None:
    async with TestClient(TestServer(create_app(Dashboard("Ada")))) as client:
        response = await client.get("/")
        body = await response.text()

    assert response.status == 200
    assert response.content_type == "text/html"
    assert "dachshund" in body


@pytest.mark.asyncio
async def test_index_with_a_description__expect_it_rendered() -> None:
    app = create_app(Dashboard("Ada", description="Code Society's Matrix bot"))

    async with TestClient(TestServer(app)) as client:
        response = await client.get("/")
        body = await response.text()

    assert "<title>Ada</title>" in body
    assert "Code Society&#39;s Matrix bot" in body
    assert "just now" in body


@pytest.mark.asyncio
async def test_index_without_a_description__expect_no_description() -> None:
    async with TestClient(TestServer(create_app(Dashboard("Ada")))) as client:
        response = await client.get("/")
        body = await response.text()

    assert "service-description" not in body


@pytest.mark.asyncio
async def test_static__expect_the_asset_served() -> None:
    async with TestClient(TestServer(create_app(Dashboard("Ada")))) as client:
        response = await client.get("/_static/dashboard.css")
        body = await response.text()

    assert response.status == 200
    assert ".card" in body


@pytest.mark.asyncio
async def test_unknown_route__expect_not_found() -> None:
    async with TestClient(TestServer(create_app(Dashboard("Ada")))) as client:
        response = await client.get("/nope")

    assert response.status == 404


def test_environment_render__expect_escaped_values() -> None:
    template = create_environment().from_string("{{ value }}")

    assert template.render(value="<script>") == "&lt;script&gt;"


@pytest.mark.asyncio
async def test_index_without_a_name__expect_a_generic_title() -> None:
    async with TestClient(TestServer(create_app(Dashboard()))) as client:
        response = await client.get("/")
        body = await response.text()

    assert f"<title>{FALLBACK_NAME}</title>" in body
