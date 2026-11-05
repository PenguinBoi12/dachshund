import logging
import threading
from typing import Any, Callable

import pytest
from aiohttp import WSServerHandshakeError, web
from aiohttp.test_utils import TestClient, TestServer
from yarl import URL

from dachshund.layout import Page
from dachshund.registry import Dashboard
from dachshund.runtime.http import create_app
from dachshund.runtime.ws import WS_PATH
from dachshund.widgets import Number, Table

TOKEN = "Bearer secret"
ALLOWED = {"Authorization": TOKEN}


def by_token(request: web.Request) -> bool:
    return request.headers.get("Authorization") == TOKEN


def build(
    authorize: Callable[[web.Request], Any] | None = by_token,
    login_url: str | None = None,
    calls: list[str] | None = None,
) -> Dashboard:
    """A public `status` page and a private `admin` page, with one action of each kind."""
    dashboard = Dashboard(
        "Ada", path=":memory:", authorize=authorize, login_url=login_url
    )
    calls = calls if calls is not None else []

    status = Page("status", public=True)

    @status.action("refresh", label="Refresh", public=True)
    def refresh(ctx) -> None:
        calls.append("refresh")

    @status.action("restart", label="Restart")
    def restart(ctx) -> None:
        calls.append("restart")

    with status.row():
        status.add(Number("uptime", actions=["refresh", "restart"]))

    admin = Page("admin")

    with admin.row():
        admin.add(Table("users", columns=["name"], loader=lambda ctx, query: ([], 0)))

    dashboard.include(admin)
    dashboard.include(status)

    return dashboard


@pytest.mark.asyncio
async def test_no_authorize__expect_every_page_and_action_open() -> None:
    calls: list[str] = []

    async with TestClient(TestServer(create_app(build(None, calls=calls)))) as client:
        admin = await client.get("/")
        status = await client.get("/status")
        action = await client.post("/_actions/restart", json={})
        rows = await client.get("/_widgets/users/page")
        body = await status.text()

    assert [admin.status, status.status, action.status, rows.status] == [200] * 4
    assert 'data-action="restart"' in body
    assert calls == ["restart"]


@pytest.mark.asyncio
async def test_denied_private_page__expect_401_and_a_basic_prompt() -> None:
    async with TestClient(TestServer(create_app(build()))) as client:
        response = await client.get("/admin", allow_redirects=False)

    assert response.status == 401
    assert response.headers["WWW-Authenticate"] == 'Basic realm="dachshund"'


@pytest.mark.asyncio
async def test_denied_private_page_with_a_login_url__expect_a_redirect() -> None:
    app = create_app(build(login_url="https://app.example/login"))

    async with TestClient(TestServer(app)) as client:
        response = await client.get("/admin", allow_redirects=False)

    location = URL(response.headers["Location"])

    assert response.status == 302
    assert str(location.with_query(None)) == "https://app.example/login"
    assert URL(location.query["next"]).path == "/admin"


@pytest.mark.asyncio
async def test_login_url_with_a_query__expect_next_appended() -> None:
    app = create_app(build(login_url="/login?app=ada"))

    async with TestClient(TestServer(app)) as client:
        response = await client.get("/admin", allow_redirects=False)

    location = URL(response.headers["Location"])

    assert (location.path, location.query["app"]) == ("/login", "ada")
    assert URL(location.query["next"]).path == "/admin"


@pytest.mark.asyncio
async def test_denied_public_page__expect_no_private_link_or_button() -> None:
    async with TestClient(TestServer(create_app(build()))) as client:
        response = await client.get("/")
        body = await response.text()

    assert response.status == 200
    assert 'data-action="refresh"' in body
    assert 'data-action="restart"' not in body
    assert 'href="/admin"' not in body


@pytest.mark.asyncio
async def test_denied_index_with_a_private_first_page__expect_the_public_one() -> None:
    async with TestClient(TestServer(create_app(build()))) as client:
        response = await client.get("/")
        body = await response.text()

    assert response.status == 200
    assert 'data-widget="uptime"' in body


@pytest.mark.asyncio
async def test_denied_index_with_no_public_page__expect_401() -> None:
    dashboard = Dashboard("Ada", path=":memory:", authorize=by_token)
    admin = Page("admin")
    with admin.row():
        admin.add(Number("users"))
    dashboard.include(admin)

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/")

    assert response.status == 401


@pytest.mark.asyncio
async def test_denied_private_action__expect_401_and_the_handler_not_called() -> None:
    calls: list[str] = []

    async with TestClient(TestServer(create_app(build(calls=calls)))) as client:
        response = await client.post("/_actions/restart", json={})
        body = await response.json()

    assert response.status == 401
    assert body["ok"] is False
    assert calls == []


@pytest.mark.asyncio
async def test_denied_public_action__expect_it_run() -> None:
    calls: list[str] = []

    async with TestClient(TestServer(create_app(build(calls=calls)))) as client:
        response = await client.post("/_actions/refresh", json={})

    assert response.status == 200
    assert calls == ["refresh"]


@pytest.mark.asyncio
async def test_denied_rows_of_a_private_table__expect_401() -> None:
    async with TestClient(TestServer(create_app(build()))) as client:
        response = await client.get("/_widgets/users/page")

    assert response.status == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["?page=admin", ""])
async def test_denied_socket_on_a_private_page__expect_no_upgrade(query: str) -> None:
    async with TestClient(TestServer(create_app(build()))) as client:
        with pytest.raises(WSServerHandshakeError) as raised:
            await client.ws_connect(f"{WS_PATH}{query}")

    assert raised.value.status == 401


@pytest.mark.asyncio
async def test_denied_socket_on_a_public_page__expect_it_upgraded() -> None:
    async with TestClient(TestServer(create_app(build()))) as client:
        async with client.ws_connect(f"{WS_PATH}?page=status") as socket:
            assert not socket.closed


@pytest.mark.asyncio
async def test_allowed__expect_every_page_link_and_button() -> None:
    calls: list[str] = []

    async with TestClient(TestServer(create_app(build(calls=calls)))) as client:
        admin = await client.get("/", headers=ALLOWED)
        status = await client.get("/status", headers=ALLOWED)
        action = await client.post("/_actions/restart", json={}, headers=ALLOWED)
        rows = await client.get("/_widgets/users/page", headers=ALLOWED)
        async with client.ws_connect(WS_PATH, headers=ALLOWED) as socket:
            assert not socket.closed
        admin_body = await admin.text()
        body = await status.text()

    assert [admin.status, status.status, action.status, rows.status] == [200] * 4
    assert 'data-widget="users"' in admin_body
    assert 'data-action="restart"' in body
    assert 'href="/"' in body
    assert calls == ["restart"]


@pytest.mark.asyncio
async def test_sync_authorize__expect_it_run_off_the_loop() -> None:
    threads: list[threading.Thread] = []

    def authorize(request: web.Request) -> bool:
        threads.append(threading.current_thread())
        return True

    async with TestClient(TestServer(create_app(build(authorize)))) as client:
        response = await client.get("/admin")

    assert response.status == 200
    assert threads and threads[0] is not threading.main_thread()


@pytest.mark.asyncio
async def test_async_authorize__expect_it_awaited() -> None:
    async def authorize(request: web.Request) -> bool:
        return request.headers.get("Authorization") == TOKEN

    async with TestClient(TestServer(create_app(build(authorize)))) as client:
        denied = await client.get("/admin")
        allowed = await client.get("/admin", headers=ALLOWED)

    assert (denied.status, allowed.status) == (401, 200)


@pytest.mark.asyncio
async def test_authorize_raising__expect_401_and_an_error_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def authorize(request: web.Request) -> bool:
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR, logger="dachshund"):
        async with TestClient(TestServer(create_app(build(authorize)))) as client:
            response = await client.get("/admin")

    assert response.status == 401
    assert "authorize() failed" in caplog.text


@pytest.mark.asyncio
async def test_authorize__expect_it_called_once_per_request() -> None:
    calls: list[str] = []

    def authorize(request: web.Request) -> bool:
        calls.append(request.path)
        return False

    async with TestClient(TestServer(create_app(build(authorize)))) as client:
        await client.get("/")

    assert calls == ["/"]


@pytest.mark.asyncio
async def test_tab_of_a_public_page__expect_it_public() -> None:
    dashboard = Dashboard("Ada", path=":memory:", authorize=by_token)
    activity = Page("activity", public=True)

    with activity.tab("commands"):
        with activity.row():
            activity.add(Number("calls"))

    dashboard.include(activity)

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/activity/commands")

    assert response.status == 200
