import asyncio
import json
from contextlib import suppress
from pathlib import Path
from typing import Any, AsyncIterator

from aiohttp import web
from jinja2 import Environment, FileSystemLoader, select_autoescape

import dachshund
from dachshund.filters import FILTERS
from dachshund.registry import Dashboard

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PACKAGE_ROOT / "templates"
STATIC_DIR = PACKAGE_ROOT / "static"
STATIC_PREFIX = "/_static"

FALLBACK_NAME = "Dashboard"
DRAIN_INTERVAL = 0.2

TEMPLATES = web.AppKey("templates", Environment)
DASHBOARD = web.AppKey("dashboard", Dashboard)


def create_environment() -> Environment:
    """Build the Jinja environment used to render the dashboard pages."""
    environment = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(default=True),
    )
    environment.filters.update(FILTERS)

    return environment


def cards(dashboard: Dashboard) -> list[dict[str, Any]]:
    """Build every widget card, filled with the events kept so far."""
    return [
        {
            "name": widget.name,
            "type": widget.type,
            "label": widget.label,
            "size": widget.size,
            "payload": json.dumps(
                widget.render(dashboard.events.events(widget.source))
            ),
        }
        for widget in dashboard.widgets.values()
    ]


async def index(request: web.Request) -> web.Response:
    """Render the dashboard page."""
    dashboard = request.app[DASHBOARD]
    template = request.app[TEMPLATES].get_template("page.html")

    html = template.render(
        name=dashboard.name or FALLBACK_NAME,
        description=dashboard.description,
        started_at=dashboard.started_at,
        widgets=cards(dashboard),
        version=dachshund.__version__,
        static_url=STATIC_PREFIX,
    )

    return web.Response(text=html, content_type="text/html")


async def drain(app: web.Application) -> None:
    """Move emitted events into the store, forever."""
    dashboard = app[DASHBOARD]

    while True:
        await asyncio.sleep(DRAIN_INTERVAL)
        dashboard.drain()


async def draining(app: web.Application) -> AsyncIterator[None]:
    """Run the drain task for as long as the application is served."""
    task = asyncio.create_task(drain(app))

    yield

    task.cancel()

    with suppress(asyncio.CancelledError):
        await task


def create_app(dashboard: Dashboard) -> web.Application:
    """Build the aiohttp application serving a dashboard.

    ## Example

    ```python
    from aiohttp.test_utils import TestClient, TestServer

    app = create_app(Dashboard("Ada"))

    async with TestClient(TestServer(app)) as client:
        response = await client.get("/")
    ```
    """
    app = web.Application()
    app[TEMPLATES] = create_environment()
    app[DASHBOARD] = dashboard

    app.router.add_get("/", index, name="index")
    app.router.add_static(STATIC_PREFIX, STATIC_DIR, name="static")

    app.cleanup_ctx.append(draining)

    return app
