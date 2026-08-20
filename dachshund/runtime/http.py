import json
from pathlib import Path
from typing import Any

from aiohttp import web
from jinja2 import Environment, FileSystemLoader, select_autoescape

import dachshund
from dachshund.actions import bind_args, invoke
from dachshund.filters import FILTERS
from dachshund.registry import Dashboard
from dachshund.runtime.keys import CLIENTS, DASHBOARD, TEMPLATES
from dachshund.widgets.base import WIDGETS, Widget
from dachshund.runtime.ws import WS_PATH, pumping, websocket

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PACKAGE_ROOT / "templates"
STATIC_DIR = PACKAGE_ROOT / "static"
STATIC_PREFIX = "/_static"
WIDGET_ASSET_PREFIX = f"{STATIC_PREFIX}/widgets"

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


def action_card(dashboard: Dashboard, name: str) -> dict[str, Any]:
    """A widget's action, as the template needs it, falling back sensibly if unregistered."""
    action = dashboard.actions.get(name)

    return {
        "name": name,
        "label": (action.label if action else None) or name,
        "confirm": action.confirm if action else False,
    }


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
                "actions": [action_card(dashboard, name) for name in widget.actions],
            }
        )

    return cards


def _asset_urls(dashboard: Dashboard, attr: str, suffix: str) -> list[str]:
    """URLs for one kind of widget-declared asset, deduped by file.

    Several widget types can share the same script/style, the three built-in
    chart types do, so this dedups by the resolved path rather than by
    `type`, which would otherwise list, fetch, and execute the same file once
    per type that points at it.
    """
    resolved: dict[Path, str] = {}

    for widget in dashboard.widgets.values():
        cls = type(widget)
        path = getattr(cls, attr)

        if path is not None:
            resolved.setdefault(path, f"{WIDGET_ASSET_PREFIX}/{cls.type}{suffix}")

    return list(resolved.values())


def widget_scripts(dashboard: Dashboard) -> list[str]:
    """The `<script>` URLs this dashboard's widgets need loaded."""
    return _asset_urls(dashboard, "script", ".js")


def widget_styles(dashboard: Dashboard) -> list[str]:
    """The `<link rel="stylesheet">` URLs this dashboard's widgets need loaded."""
    return _asset_urls(dashboard, "style", ".css")


async def widget_file(request: web.Request, attr: str) -> web.FileResponse:
    """Serve the file one widget type declared for `attr` ("script"/"style")."""
    cls = WIDGETS.get(request.match_info["type"])
    path = getattr(cls, attr, None) if cls else None

    if path is None:
        raise web.HTTPNotFound()

    return web.FileResponse(path)


async def widget_script(request: web.Request) -> web.FileResponse:
    return await widget_file(request, "script")


async def widget_style(request: web.Request) -> web.FileResponse:
    return await widget_file(request, "style")


async def index(request: web.Request) -> web.Response:
    """Render the dashboard page."""
    dashboard = request.app[DASHBOARD]
    template = request.app[TEMPLATES].get_template("page.html")

    html = template.render(
        name=dashboard.name or FALLBACK_NAME,
        description=dashboard.description,
        started_at=dashboard.started_at,
        widgets=await cards(dashboard),
        widget_scripts=widget_scripts(dashboard),
        widget_styles=widget_styles(dashboard),
        version=dachshund.__version__,
        static_url=STATIC_PREFIX,
    )

    return web.Response(text=html, content_type="text/html")


async def run_action(request: web.Request) -> web.Response:
    """Run an action and report what it returned, or how it failed."""
    dashboard = request.app[DASHBOARD]
    name = request.match_info["name"]
    action = dashboard.actions.get(name)

    if action is None:
        return web.json_response(
            {"ok": False, "error": f"No action named {name!r}."}, status=404
        )

    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)

    try:
        kwargs = bind_args(action.handler, body.get("args", {}))
    except TypeError as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=400)

    try:
        result = await invoke(action, kwargs, dashboard.host_loop)
    except Exception as exc:
        return web.json_response({"ok": False, "error": str(exc)}, status=500)

    return web.json_response({"ok": True, "result": result})


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
    app.router.add_get(
        f"{WIDGET_ASSET_PREFIX}/{{type}}.js", widget_script, name="widget-script"
    )
    app.router.add_get(
        f"{WIDGET_ASSET_PREFIX}/{{type}}.css", widget_style, name="widget-style"
    )
    app.router.add_post("/_actions/{name}", run_action, name="action")
    app.router.add_static(STATIC_PREFIX, STATIC_DIR, name="static")

    app.cleanup_ctx.append(pumping)

    return app
