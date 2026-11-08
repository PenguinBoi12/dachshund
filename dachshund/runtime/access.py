import logging
from urllib.parse import urlencode

from aiohttp import web
from yarl import URL

from dachshund.actions import run
from dachshund.registry import LOGIN_PREFIX, Dashboard
from dachshund.runtime.keys import DASHBOARD

AUTHORIZED = "dachshund.authorized"

logger = logging.getLogger("dachshund")


def login_page(dashboard: Dashboard) -> str | None:
    """Where a denied page redirects: `login_url`, or the `login` handler."""
    return f"{LOGIN_PREFIX}/login" if dashboard.login else dashboard.login_url


def is_same_origin(request: web.Request) -> bool:
    """Whether `request` comes from a page of this dashboard, or from outside a browser.

    A browser sends `Origin` with a WebSocket or a `fetch()`. It has to match
    the dashboard's host, or the host a reverse proxy forwarded it from.
    """
    origin = request.headers.get("Origin")

    if origin is None:
        return True

    try:
        sent = URL(origin)
        hosts = [request.host, *request.headers.get("X-Forwarded-Host", "").split(",")]

        return any(
            host.strip()
            and (
                URL.build(scheme=sent.scheme, authority=host.strip()).origin()
                == sent.origin()
            )
            for host in hosts
        )
    except ValueError:
        return False


def is_public_page(dashboard: Dashboard, path: str) -> bool:
    """Whether the page at `path` is shown without `authorize`, a tab following its page."""
    page = dashboard.pages.get(path)

    while page is not None and page.parent is not None:
        page = page.parent

    return page is not None and page.public


def is_public_action(dashboard: Dashboard, name: str) -> bool:
    action = dashboard.actions.get(name)

    return action is not None and action.public


async def is_authorized(request: web.Request) -> bool:
    """Whether the dashboard's `authorize` lets `request` in, asked once per request."""
    if AUTHORIZED not in request:
        dashboard = request.app[DASHBOARD]

        if dashboard.authorize is None:
            request[AUTHORIZED] = True
        else:
            try:
                allowed = await run(
                    dashboard.authorize, request, host_loop=dashboard.host_loop
                )
            except Exception:
                logger.exception("authorize() failed, denying the request.")
                allowed = False

            request[AUTHORIZED] = bool(allowed)

    return bool(request[AUTHORIZED])


async def can_see_page(request: web.Request, path: str) -> bool:
    return is_public_page(request.app[DASHBOARD], path) or await is_authorized(request)


async def can_run_action(request: web.Request, name: str) -> bool:
    return is_public_action(request.app[DASHBOARD], name) or await is_authorized(
        request
    )


async def runnable_actions(request: web.Request) -> set[str]:
    """The names of the actions `request` may run."""
    dashboard = request.app[DASHBOARD]

    return {name for name in dashboard.actions if await can_run_action(request, name)}


def login_location(request: web.Request) -> str | None:
    """The login page, coming back to `request`'s URL, `None` without one."""
    login_url = login_page(request.app[DASHBOARD])

    if login_url is None:
        return None

    separator = "&" if "?" in login_url else "?"
    return f"{login_url}{separator}{urlencode({'next': str(request.url)})}"


async def account(request: web.Request) -> dict[str, str] | None:
    """The footer's log in or log out link, `None` without a login page."""
    dashboard = request.app[DASHBOARD]
    location = login_location(request)

    if dashboard.authorize is None or location is None:
        return None

    if not await is_authorized(request):
        return {"label": "Log in", "url": location}

    if "logout" in dashboard.login:
        return {"label": "Log out", "url": f"{LOGIN_PREFIX}/logout"}

    return None


def denied(request: web.Request, *, page: bool) -> web.HTTPException:
    """What a denied request gets: a login redirect or prompt for a page, 401 otherwise."""
    location = login_location(request)

    if page and location:
        return web.HTTPFound(location)

    if page:
        return web.HTTPUnauthorized(
            headers={"WWW-Authenticate": 'Basic realm="dachshund"'}
        )

    return web.HTTPUnauthorized()
