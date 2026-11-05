import json
from pathlib import Path
from typing import Any, Collection

from aiohttp import web
from jinja2 import Environment, FileSystemLoader, select_autoescape

import dachshund
from dachshund.actions import action_card, bind_args, invoke, resolve_row_actions
from dachshund.filters import FILTERS
from dachshund.layout import DEFAULT_PAGE, Page
from dachshund.registry import Dashboard
from dachshund.runtime.access import (
    can_run_action,
    can_see_page,
    denied,
    runnable_actions,
)
from dachshund.runtime.keys import CLIENTS, DASHBOARD, TEMPLATES
from dachshund.widgets.base import WIDGETS, Widget
from dachshund.widgets.query import TableQuery
from dachshund.runtime.ws import WS_PATH, pumping, websocket

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PACKAGE_ROOT / "templates"
STATIC_DIR = PACKAGE_ROOT / "static"
STATIC_PREFIX = "/_static"
WIDGET_ASSET_PREFIX = f"{STATIC_PREFIX}/widgets"

FALLBACK_NAME = "Dashboard"
DEFAULT_PAGE_TITLE = "Overview"
MAX_LIMIT = 100


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


async def card(
    dashboard: Dashboard, widget: Widget, runnable: Collection[str] | None = None
) -> dict[str, Any]:
    """Build one widget's card, filled with the events kept so far.

    A widget that renders its own actions (a table, one button per row)
    gets no card-level action row, `page.html`'s `.card-actions` block is
    for widgets that don't place buttons themselves. Its rows get the
    resolved `{name, label, confirm}` actions instead, so the renderer never
    has to look up `dashboard.actions` on its own.

    With `runnable`, actions not in it get no button.
    """
    kept = await dashboard.events.events(widget.source)
    payload = (
        await widget.page(kept, TableQuery(), dashboard.context, dashboard.host_loop)
        if widget.paginated
        else widget.render(kept)
    )
    resolve_row_actions(dashboard.actions, widget, payload, runnable)

    return {
        "name": widget.name,
        "type": widget.type,
        "title": heading(widget),
        "payload": json.dumps(payload),
        "actions": (
            []
            if widget.renders_own_actions
            else [
                action_card(dashboard.actions, name, widget.action_args.get(name))
                for name in widget.actions
                if runnable is None or name in runnable
            ]
        ),
    }


async def cards(
    dashboard: Dashboard,
    page: str = DEFAULT_PAGE,
    runnable: Collection[str] | None = None,
) -> list[list[dict[str, Any]]]:
    """Build the cards of `page`: a list per row, of `{"span", "cards"}` per column."""
    rows = []

    for row in dashboard.layout(page):
        columns = []

        for column, span in zip(row.columns, row.spans()):
            cards = [
                await card(dashboard, dashboard.widgets[name], runnable)
                for name in column.names
            ]
            columns.append({"span": span, "cards": cards})

        rows.append(columns)

    return rows


def page_names(dashboard: Dashboard) -> list[str]:
    """The top-level pages worth showing, in navigation order.

    `"default"` comes first, unless other pages are declared and it has
    no widgets left on it.
    """
    declared = [
        name
        for name, page in dashboard.pages.items()
        if page.parent is None and name != DEFAULT_PAGE
    ]

    if not declared or dashboard.layout(DEFAULT_PAGE):
        return [DEFAULT_PAGE, *declared]

    return declared


def shown(dashboard: Dashboard, path: str) -> str:
    """The page actually drawn for `path`, its first tab if it has tabs."""
    page = dashboard.pages.get(path)

    while page is not None and page.tabs:
        page = next(iter(page.tabs.values()))

    return page.path if page is not None else path


def page_title(dashboard: Dashboard, name: str) -> str:
    """What a page is called in the navigation."""
    declared = dashboard.pages.get(name)

    if declared is not None and declared.title:
        return declared.title

    if name == DEFAULT_PAGE:
        return DEFAULT_PAGE_TITLE

    return name.rsplit("/", 1)[-1].replace("_", " ")


def tab_links(dashboard: Dashboard, path: str) -> list[dict[str, Any]]:
    """The tab bar for the page at `path`, empty unless it's a tab."""
    page = dashboard.pages.get(path)
    parent: Page | None = page.parent if page is not None else None

    if parent is None:
        return []

    return [
        {
            "url": f"/{tab.path}",
            "title": page_title(dashboard, tab.path),
            "current": tab.path == path,
        }
        for tab in parent.tabs.values()
    ]


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


def table_query(request: web.Request) -> TableQuery:
    """The `TableQuery` a request's query string asks for."""
    params = request.query
    limit = _integer(params.get("limit"))

    return TableQuery(
        search=params.get("search") or None,
        sort_by=params.get("sort") or None,
        descending=params.get("dir") == "desc",
        offset=max(0, _integer(params.get("offset"))),
        limit=min(limit, MAX_LIMIT) if limit > 0 else None,
    )


def _integer(value: str | None) -> int:
    try:
        return int(value or 0)
    except ValueError:
        return 0


async def widget_page(request: web.Request) -> web.Response:
    """One page of a paginated widget's current rows.

    `?search=`, `?sort=`, `?dir=desc`, `?offset=` and `?limit=` make up the
    widget's `TableQuery`.
    """
    dashboard = request.app[DASHBOARD]
    widget = dashboard.widgets.get(request.match_info["name"])

    if widget is None or not widget.paginated:
        raise web.HTTPNotFound()

    if not await can_see_page(request, dashboard.widget_page(widget.name)):
        raise denied(request, page=False)

    kept = await dashboard.events.events(widget.source)
    payload = await widget.page(
        kept, table_query(request), dashboard.context, dashboard.host_loop
    )
    resolve_row_actions(
        dashboard.actions, widget, payload, await runnable_actions(request)
    )

    return web.json_response(payload)


async def render_page(request: web.Request, path: str) -> web.Response:
    """Render one page of the dashboard, `"parent/tab"` for a tab."""
    dashboard = request.app[DASHBOARD]
    template = request.app[TEMPLATES].get_template("page.html")
    names = await visible_pages(request)
    page = shown(dashboard, path)
    top = page.split("/", 1)[0]
    rows = await cards(dashboard, page, await runnable_actions(request))

    html = template.render(
        name=dashboard.name or FALLBACK_NAME,
        description=dashboard.description,
        started_at=dashboard.started_at,
        page=page,
        heading=page_title(dashboard, top),
        rows=rows,
        pages=[
            {
                "url": "/" if name == names[0] else f"/{name}",
                "title": page_title(dashboard, name),
                "current": name == top,
            }
            for name in names
        ],
        tabs=tab_links(dashboard, page),
        widget_scripts=widget_scripts(dashboard),
        widget_styles=widget_styles(dashboard),
        version=dachshund.__version__,
        static_url=STATIC_PREFIX,
    )

    return web.Response(text=html, content_type="text/html")


async def visible_pages(request: web.Request) -> list[str]:
    """The top-level pages `request` may see, in navigation order."""
    return [
        name
        for name in page_names(request.app[DASHBOARD])
        if await can_see_page(request, name)
    ]


async def index(request: web.Request) -> web.Response:
    """Render the first page the visitor may see."""
    names = await visible_pages(request)

    if not names:
        raise denied(request, page=True)

    return await render_page(request, names[0])


async def named_page(request: web.Request) -> web.Response:
    """Render the page named in the URL, the first one redirecting to `/`."""
    page = request.match_info["page"]

    if page not in page_names(request.app[DASHBOARD]):
        raise web.HTTPNotFound()

    if not await can_see_page(request, page):
        raise denied(request, page=True)

    if page == (await visible_pages(request))[0]:
        raise web.HTTPFound("/")

    return await render_page(request, page)


async def named_tab(request: web.Request) -> web.Response:
    """Render the tab named in the URL."""
    path = f"{request.match_info['page']}/{request.match_info['tab']}"
    page = request.app[DASHBOARD].pages.get(path)

    if page is None or page.parent is None:
        raise web.HTTPNotFound()

    if not await can_see_page(request, path):
        raise denied(request, page=True)

    return await render_page(request, path)


async def run_action(request: web.Request) -> web.Response:
    """Run an action and report what it returned, or how it failed."""
    dashboard = request.app[DASHBOARD]
    name = request.match_info["name"]
    action = dashboard.actions.get(name)

    if action is None:
        return web.json_response(
            {"ok": False, "error": f"No action named {name!r}."}, status=404
        )

    if not await can_run_action(request, name):
        return web.json_response({"ok": False, "error": "Not authorized."}, status=401)

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
    app[CLIENTS] = {}

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
    app.router.add_get("/{page}/{tab}", named_tab, name="tab")

    app.cleanup_ctx.append(pumping)

    return app
