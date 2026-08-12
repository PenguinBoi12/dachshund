from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web
from jinja2 import Environment, FileSystemLoader, select_autoescape

import dachshund
from dachshund.filters import FILTERS

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PACKAGE_ROOT / "templates"
STATIC_DIR = PACKAGE_ROOT / "static"
STATIC_PREFIX = "/_static"

FALLBACK_NAME = "Dashboard"

TEMPLATES = web.AppKey("templates", Environment)
CONTEXT = web.AppKey("context", dict)


def create_environment() -> Environment:
    """Build the Jinja environment used to render the dashboard pages.

    Autoescaping is always on: widget data carries application content that
    must never be trusted as markup.
    """
    environment = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(default=True),
    )
    environment.filters.update(FILTERS)

    return environment


async def index(request: web.Request) -> web.Response:
    """Render the dashboard page."""
    template = request.app[TEMPLATES].get_template("page.html")
    html = template.render(**request.app[CONTEXT])

    return web.Response(text=html, content_type="text/html")


def create_app(
    *,
    name: str | None = None,
    description: str | None = None,
    started_at: datetime | None = None,
) -> web.Application:
    """Build the aiohttp application serving a dashboard.

    ## Example

    ```python
    from aiohttp.test_utils import TestClient, TestServer

    async with TestClient(TestServer(create_app(name="Ada"))) as client:
        response = await client.get("/")
    ```
    """
    app = web.Application()
    app[TEMPLATES] = create_environment()
    app[CONTEXT] = {
        "name": name or FALLBACK_NAME,
        "description": description,
        "started_at": started_at or datetime.now(tz=timezone.utc),
        "version": dachshund.__version__,
        "static_url": STATIC_PREFIX,
    }

    app.router.add_get("/", index, name="index")
    app.router.add_static(STATIC_PREFIX, STATIC_DIR, name="static")

    return app
