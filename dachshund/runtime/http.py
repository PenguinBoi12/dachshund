import json
from pathlib import Path
from typing import Any

from aiohttp import web
from jinja2 import Environment, FileSystemLoader, select_autoescape

import dachshund
from dachshund.actions import action_card, bind_args, invoke, resolve_row_actions
from dachshund.filters import FILTERS
from dachshund.layout import DEFAULT_PAGE
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
DEFAULT_PAGE_TITLE = "Overview"


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


async def card(dashboard: Dashboard, widget: Widget) -> dict[str, Any]:
    """Build one widget's card, filled with the events kept so far.

    A widget that renders its own actions (a table, one button per row)
    gets no card-level action row, `page.html`'s `.card-actions` block is
    for widgets that don't place buttons themselves. Its rows get the
    resolved `{name, label, confirm}` actions instead, so the renderer never
    has to look up `dashboard.actions` on its own.
    """
    kept = await dashboard.events.events(widget.source)
    payload = (
        await widget.page(kept, None, dashboard.context, dashboard.host_loop)
        if widget.paginated
        else widget.render(kept)
    )
    resolve_row_actions(dashboard.actions, widget, payload)

    return {
        "name": widget.name,
        "type": widget.type,
        "title": heading(widget),
        "size": widget.size,
        "payload": json.dumps(payload),
        "actions": []
        if widget.renders_own_actions
        else [
            action_card(dashboard.actions, name, widget.action_args.get(name))
            for name in widget.actions
        ],
    }


async def cards(
    dashboard: Dashboard, page: str = DEFAULT_PAGE
) -> list[list[dict[str, Any]]]:
    """Build the cards of `page`, one list per row, in display order."""
    return [
        [await card(dashboard, dashboard.widgets[name]) for name in row]
        for row in dashboard.layout(page)
    ]


def page_names(dashboard: Dashboard) -> list[str]:
    """The pages worth showing, in navigation order.

    `"default"` comes first, unless other pages are declared and it has
    no widgets left on it.
    """
    declared = [name for name in dashboard.pages if name != DEFAULT_PAGE]

    if not declared or dashboard.layout(DEFAULT_PAGE):
        return [DEFAULT_PAGE, *declared]

    return declared


def page_title(dashboard: Dashboard, name: str) -> str:
    """What a page is called in the navigation."""
    declared = dashboard.pages.get(name)

    if declared is not None and declared.title:
        return declared.title

    return DEFAULT_PAGE_TITLE if name == DEFAULT_PAGE else name.replace("_", " ")


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


async def widget_page(request: web.Request) -> web.Response:
    """One page of a paginated widget's current rows, after `?cursor=`."""
    dashboard = request.app[DASHBOARD]
    widget = dashboard.widgets.get(request.match_info["name"])

    if widget is None or not widget.paginated:
        raise web.HTTPNotFound()

    cursor = request.query.get("cursor")
    kept = await dashboard.events.events(widget.source)
    payload = await widget.page(kept, cursor, dashboard.context, dashboard.host_loop)
    resolve_row_actions(dashboard.actions, widget, payload)

    return web.json_response(payload)


async def render_page(request: web.Request, page: str) -> web.Response:
    """Render one page of the dashboard."""
    dashboard = request.app[DASHBOARD]
    template = request.app[TEMPLATES].get_template("page.html")
    names = page_names(dashboard)

    html = template.render(
        name=dashboard.name or FALLBACK_NAME,
        description=dashboard.description,
        started_at=dashboard.started_at,
        rows=await cards(dashboard, page),
        pages=[
            {
                "url": "/" if name == names[0] else f"/{name}",
                "title": page_title(dashboard, name),
                "current": name == page,
            }
            for name in names
        ],
        widget_scripts=widget_scripts(dashboard),
        widget_styles=widget_styles(dashboard),
        version=dachshund.__version__,
        static_url=STATIC_PREFIX,
    )

    return web.Response(text=html, content_type="text/html")


async def index(request: web.Request) -> web.Response:
    """Render the first page of the dashboard."""
    return await render_page(request, page_names(request.app[DASHBOARD])[0])


async def named_page(request: web.Request) -> web.Response:
    """Render the page named in the URL, the first one redirecting to `/`."""
    page = request.match_info["page"]
    names = page_names(request.app[DASHBOARD])

    if page not in names:
        raise web.HTTPNotFound()

    if page == names[0]:
        raise web.HTTPFound("/")

    return await render_page(request, page)


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
        result = await invoke(action, kwargs, dashboard.context, dashboard.host_loop)
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
    app.router.add_get("/_widgets/{name}/page", widget_page, name="widget-page")
    app.router.add_static(STATIC_PREFIX, STATIC_DIR, name="static")
    # Last, so a page name never shadows one of the routes above.
    app.router.add_get("/{page}", named_page, name="page")

    app.cleanup_ctx.append(pumping)

    return app
