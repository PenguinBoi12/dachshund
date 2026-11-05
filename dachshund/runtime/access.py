import logging
from urllib.parse import urlencode

from aiohttp import web

from dachshund.actions import run
from dachshund.registry import Dashboard
from dachshund.runtime.keys import DASHBOARD

AUTHORIZED = "dachshund.authorized"

logger = logging.getLogger("dachshund")


def is_public_page(dashboard: Dashboard, path: str) -> bool:
    """Whether the page at `path` is shown without `authorize`, a tab following its page."""
    page = dashboard.pages.get(path)

    while page is not None and page.parent is not None:
        page = page.parent

    return page is not None and page.public


def is_public_action(dashboard: Dashboard, name: str) -> bool:
    action = dashboard.actions.get(name)

    return action is not None and action.public


async def authorized(request: web.Request) -> bool:
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
    return is_public_page(request.app[DASHBOARD], path) or await authorized(request)


async def can_run_action(request: web.Request, name: str) -> bool:
    return is_public_action(request.app[DASHBOARD], name) or await authorized(request)


async def runnable_actions(request: web.Request) -> set[str]:
    """The names of the actions `request` may run."""
    dashboard = request.app[DASHBOARD]

    return {name for name in dashboard.actions if await can_run_action(request, name)}


def denied(request: web.Request, *, page: bool) -> web.HTTPException:
    """What a denied request gets: a login redirect or prompt for a page, 401 otherwise."""
    login_url = request.app[DASHBOARD].login_url

    if page and login_url:
        separator = "&" if "?" in login_url else "?"
        query = urlencode({"next": str(request.url)})
        return web.HTTPFound(f"{login_url}{separator}{query}")

    if page:
        return web.HTTPUnauthorized(
            headers={"WWW-Authenticate": 'Basic realm="dachshund"'}
        )

    return web.HTTPUnauthorized()
