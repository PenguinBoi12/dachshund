import json
from pathlib import Path
from typing import Any

from aiohttp import web
from jinja2 import Environment, FileSystemLoader, select_autoescape

import dachshund
from dachshund.filters import FILTERS
from dachshund.registry import Dashboard
from dachshund.runtime.keys import CLIENTS, DASHBOARD, TEMPLATES
from dachshund.widgets.base import Widget
from dachshund.runtime.ws import WS_PATH, pumping, websocket

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PACKAGE_ROOT / "templates"
STATIC_DIR = PACKAGE_ROOT / "static"
STATIC_PREFIX = "/_static"

FALLBACK_NAME = "Dashboard"


def create_environment() -> Environment:
    """Build the Jinja environment used to render the dashboard pages."""
    environment = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(default=True),
    )
    environment.filters.update(FILTERS)

    return environment


def heading(widget: Widget) -> str:
    """What a card says, falling back to a readable form of the widget's name."""
    return widget.title or widget.name.replace("_", " ")


async def cards(dashboard: Dashboard) -> list[dict[str, Any]]:
    """Build every widget card, filled with the events kept so far."""
    cards = []

    for widget in dashboard.widgets.values():
        kept = await dashboard.events.events(widget.source)
        cards.append(
            {
                "name": widget.name,
                "type": widget.type,
                "title": heading(widget),
                "size": widget.size,
                "payload": json.dumps(widget.render(kept)),
            }
        )

    return cards


async def index(request: web.Request) -> web.Response:
    """Render the dashboard page."""
    dashboard = request.app[DASHBOARD]
    template = request.app[TEMPLATES].get_template("page.html")

    html = template.render(
        name=dashboard.name or FALLBACK_NAME,
        description=dashboard.description,
        started_at=dashboard.started_at,
        widgets=await cards(dashboard),
        version=dachshund.__version__,
        static_url=STATIC_PREFIX,
    )

    return web.Response(text=html, content_type="text/html")


def create_app(dashboard: Dashboard) -> web.Application:
    """Build the aiohttp application serving a dashboard.

    ## Example

    ```python
    from aiohttp.test_utils import TestClient, TestServer

    app = create_app(Dashboard("Ada", path=":memory:"))

    async with TestClient(TestServer(app)) as client:
        response = await client.get("/")
    ```
    """
    app = web.Application()
    app[TEMPLATES] = create_environment()
    app[DASHBOARD] = dashboard
    app[CLIENTS] = set()

    app.router.add_get("/", index, name="index")
    app.router.add_get(WS_PATH, websocket, name="websocket")
    app.router.add_static(STATIC_PREFIX, STATIC_DIR, name="static")

    app.cleanup_ctx.append(pumping)

    return app
