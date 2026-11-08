from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from yarl import URL

import dachshund
from dachshund import registry
from dachshund.layout import Page
from dachshund.registry import Dashboard
from dachshund.runtime.access import login_page
from dachshund.runtime.http import create_app
from dachshund.widgets import Number


async def login(request: web.Request) -> web.Response:
    return web.Response(text=f"login, next={request.query.get('next')}")


async def callback(request: web.Request) -> web.Response:
    found = web.HTTPFound("/")
    found.set_cookie("session", "ada")
    raise found


def private_dashboard(**options: Any) -> Dashboard:
    dashboard = Dashboard(
        "Ada",
        path=":memory:",
        authorize=lambda request: request.cookies.get("session") == "ada",
        **options,
    )
    admin = Page("admin")
    with admin.row():
        admin.add(Number("users"))
    dashboard.include(admin)

    return dashboard


@pytest.mark.asyncio
async def test_login_handlers__expect_them_served_publicly_under_login() -> None:
    dashboard = private_dashboard(login={"login": login, "callback": callback})

    async with TestClient(TestServer(create_app(dashboard))) as client:
        page = await client.get("/_auth/login")
        posted = await client.post("/_auth/callback", allow_redirects=False)
        body = await page.text()

    assert (page.status, body) == (200, "login, next=None")
    assert posted.status == 302
    assert posted.cookies["session"].value == "ada"


@pytest.mark.asyncio
async def test_denied_page_with_login__expect_a_redirect_to_its_login_handler() -> None:
    dashboard = private_dashboard(login={"login": login})

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/admin", allow_redirects=False)

    location = URL(response.headers["Location"])

    assert response.status == 302
    assert location.path == "/_auth/login"
    assert URL(location.query["next"]).path == "/admin"


@pytest.mark.asyncio
async def test_after_login__expect_the_private_page() -> None:
    dashboard = private_dashboard(login={"login": login, "callback": callback})

    async with TestClient(TestServer(create_app(dashboard))) as client:
        await client.get("/_auth/callback", allow_redirects=False)
        response = await client.get("/admin")
        body = await response.text()

    assert response.status == 200
    assert 'data-widget="users"' in body


@pytest.mark.asyncio
async def test_without_login__expect_login_paths_not_served() -> None:
    dashboard = private_dashboard(login_url="https://app.example/login")

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/_auth/login", allow_redirects=False)

    assert response.status == 404


@pytest.mark.parametrize(
    "options, message",
    [
        ({"login": {"login": login}, "login_url": "/login"}, "not both"),
        ({"login": {"callback": callback}}, "needs a 'login' handler"),
        ({"login": {"login": login, "a/b": callback}}, "one path segment"),
    ],
)
def test_login_with_bad_options__expect_value_error(
    options: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        Dashboard(path=":memory:", **options)


def test_login_on_a_running_dashboard__expect_runtime_error() -> None:
    try:
        dachshund.init(port=0, path=":memory:")

        with pytest.raises(RuntimeError, match="before the dashboard starts"):
            dachshund.init(port=0, path=":memory:", login={"login": login})
    finally:
        dachshund.shutdown()
        registry._dashboard = None


def test_init_with_login__expect_it_set() -> None:
    try:
        dashboard = dachshund.init(port=0, path=":memory:", login={"login": login})
        assert login_page(dashboard) == "/_auth/login"
    finally:
        dachshund.shutdown()
        registry._dashboard = None


@pytest.mark.parametrize("name", ["_auth", "_ws"])
def test_page_named_with_an_underscore__expect_value_error(name: str) -> None:
    with pytest.raises(ValueError, match="dachshund's own"):
        Page(name)


async def logout(request: web.Request) -> web.Response:
    found = web.HTTPFound("/")
    found.del_cookie("session")
    raise found


async def footer(dashboard: Dashboard, cookies: dict[str, str] | None = None) -> str:
    public = Page("status", public=True)
    with public.row():
        public.add(Number("uptime"))
    dashboard.include(public)

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.get("/status", cookies=cookies or {})
        body = await response.text()

    return body.split("<footer")[1]


@pytest.mark.asyncio
async def test_footer_logged_out__expect_a_log_in_link_coming_back_here() -> None:
    dashboard = private_dashboard(login={"login": login, "logout": logout})

    html = await footer(dashboard)

    assert ">Log in</a>" in html
    assert 'href="/_auth/login?next=http%3A%2F%2F' in html


@pytest.mark.asyncio
async def test_footer_logged_in__expect_a_log_out_link() -> None:
    dashboard = private_dashboard(login={"login": login, "logout": logout})

    html = await footer(dashboard, {"session": "ada"})

    assert '<a class="account-link" href="/_auth/logout">Log out</a>' in html


@pytest.mark.asyncio
async def test_footer_logged_in_without_a_logout_handler__expect_no_link() -> None:
    html = await footer(private_dashboard(login={"login": login}), {"session": "ada"})

    assert "account-link" not in html


@pytest.mark.asyncio
async def test_footer_with_a_login_url__expect_log_in_to_it() -> None:
    dashboard = private_dashboard(login_url="https://app.example/login")

    html = await footer(dashboard)

    assert 'href="https://app.example/login?next=' in html


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "options",
    [{}, {"authorize": lambda request: False}],
    ids=["without authorize", "basic only"],
)
async def test_footer_without_a_login_page__expect_no_link(options: dict) -> None:
    html = await footer(Dashboard("Ada", path=":memory:", **options))

    assert "account-link" not in html
