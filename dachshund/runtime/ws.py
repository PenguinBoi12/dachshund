import asyncio
import logging
from contextlib import suppress
from typing import Any, AsyncIterator

from aiohttp import WSCloseCode, web

from dachshund.actions import resolve_row_actions
from dachshund.layout import DEFAULT_PAGE
from dachshund.registry import Dashboard
from dachshund.runtime import render
from dachshund.runtime.access import can_see_page, denied, is_authorized, is_same_origin
from dachshund.runtime.keys import CLIENTS, DASHBOARD
from dachshund.storage.events import Event
from dachshund.widgets.base import Widget
from dachshund.widgets.persistable import PersistableWidget, is_persisting

WS_PATH = "/_ws"
PUMP_INTERVAL = 0.2
HEARTBEAT = 30.0

logger = logging.getLogger("dachshund")


def live_op(widget: Widget) -> str:
    """How a page applies `widget`'s updates: a windowed widget is redrawn whole."""
    return "replace" if widget.window() is not None else widget.op


def message(widget: Widget, data: dict[str, Any]) -> dict[str, Any]:
    """Build what a page applies to one widget."""
    return {"widget": widget.name, "op": live_op(widget), "data": data}


def distinct_fields(dashboard: Dashboard) -> dict[str, set[str]]:
    """The fields whose distinct values compaction keeps, by source."""
    fields: dict[str, set[str]] = {}

    for widget in dashboard.widgets.values():
        window = widget.window()

        if window is not None and window.aggregate == "distinct":
            fields.setdefault(widget.source, set()).update(window.fields)

    return fields


def kept_raw(dashboard: Dashboard) -> dict[str, int]:
    """How many of its newest events each source keeps raw, the largest asked."""
    keep: dict[str, int] = {}

    for widget in dashboard.widgets.values():
        lines = widget.raw_events()

        if lines is not None:
            keep[widget.source] = max(keep.get(widget.source, 1), lines)

    return keep


async def updates(dashboard: Dashboard, events: list[Event]) -> list[dict[str, Any]]:
    """Build what the open pages need to apply for a batch of events.

    An event updates every widget watching its source, so one emit can
    update several widgets.

    ## Example

    ```python
    dashboard = Dashboard(path=":memory:")
    with dashboard.row():
        dashboard.add(TimeSeriesChart("latency"))
    dashboard.emit("latency", value=96)

    events = dashboard.queue.drain()
    await dashboard.events.append(events)
    await updates(dashboard, events)
    # [{"widget": "latency", "op": "append", "data": {"x": ..., "y": [96.0]}}]
    ```
    """
    messages = []
    rebuilt: dict[str, Widget] = {}
    persisted: dict[str, PersistableWidget] = {}

    for event in events:
        watching = [w for w in dashboard.widgets.values() if w.source == event.source]

        for widget in watching:
            if is_persisting(widget):
                widget.accumulate(event)
                persisted[widget.name] = widget

            if live_op(widget) != "append":
                rebuilt[widget.name] = widget
                continue

            change = widget.update(event)

            if change is not None:
                messages.append(message(widget, change))

    if dashboard.storage is not None:
        for widget in persisted.values():
            try:
                await dashboard.storage.save(widget.name, widget.snapshot())
            except Exception:
                logger.exception("Could not persist %r's state.", widget.name)

    for widget in rebuilt.values():
        if widget.paginated:
            messages.append(message(widget, {}))
            continue

        payload = await render.payload(dashboard, widget)
        resolve_row_actions(dashboard.actions, widget, payload)
        messages.append(message(widget, payload))

    return messages


async def hydrate(dashboard: Dashboard, hydrated: set[str] | None = None) -> None:
    """Seed every not-yet-hydrated persisting widget from storage.

    `hydrated` names widgets already seeded and grows with each one newly
    seeded here, so calling this again for whatever's been registered since
    never re-restores (and so never clobbers with a stale snapshot) a widget
    already accumulating live updates. Left unset, this is a one-shot pass
    over everything currently registered.

    ## Example

    ```python
    await hydrate(dashboard)
    ```
    """
    if dashboard.storage is None:
        return

    if hydrated is None:
        hydrated = set()

    for widget in dashboard.widgets.values():
        if widget.name in hydrated or not is_persisting(widget):
            continue

        try:
            data = await dashboard.storage.load(widget.name)
        except Exception:
            logger.exception("Could not load %r's persisted state.", widget.name)
            continue

        hydrated.add(widget.name)

        if data is not None:
            widget.restore(data)


async def broadcast(app: web.Application, messages: list[dict[str, Any]]) -> None:
    """Push a batch of updates to every open page.

    Each page only gets the updates for widgets it shows, a page with
    nothing left to apply isn't sent anything. Pages that have gone away
    are dropped rather than retried.
    """
    if not messages:
        return

    dashboard = app[DASHBOARD]
    clients = app[CLIENTS]
    pages = {
        name: dashboard.placements.get(name, DEFAULT_PAGE)
        for name in {message["widget"] for message in messages}
    }

    for client, page in list(clients.items()):
        relevant = [
            message
            for message in messages
            if page is None or pages[message["widget"]] == page
        ]

        if not relevant:
            continue

        try:
            await client.send_json(relevant)
        except (ConnectionResetError, RuntimeError):
            clients.pop(client, None)


async def pump(app: web.Application, hydrated: set[str] | None = None) -> None:
    """Move emitted events into the store and out to the open pages.

    This is the only place the store is written, so it needs no locking. It
    always runs on the runtime's event loop. Each tick also hydrates
    whatever persisting widget hasn't been seeded yet, e.g. one registered
    after the dashboard was already serving.

    ## Example

    ```python
    asyncio.create_task(pump(app))
    ```
    """
    dashboard = app[DASHBOARD]

    while True:
        await asyncio.sleep(PUMP_INTERVAL)

        try:
            await hydrate(dashboard, hydrated)

            events = dashboard.queue.drain()
            await dashboard.events.append(events)

            await dashboard.events.compact(
                distinct_fields(dashboard), kept_raw(dashboard)
            )

            await broadcast(app, await updates(dashboard, events))
        except Exception:
            logger.exception("Dropped a batch of dashboard updates.")


async def pumping(app: web.Application) -> AsyncIterator[None]:
    """Run the pump for as long as the application is served.

    Persisting widgets are hydrated first, before the site accepts any
    connections, so the very first page load already reflects them. One
    registered later, after the dashboard already started, is hydrated the
    same way on the next pump tick instead.
    """
    hydrated: set[str] = set()

    await hydrate(app[DASHBOARD], hydrated)

    task = asyncio.create_task(pump(app, hydrated))

    yield

    task.cancel()

    with suppress(asyncio.CancelledError):
        await task

    clients = app[CLIENTS]

    for client in list(clients):
        await client.close(code=WSCloseCode.GOING_AWAY, message=b"shutting down")


async def websocket(request: web.Request) -> web.WebSocketResponse:
    """Hold a page's connection open for as long as it is looking.

    `?page=` names the dashboard page it shows, so it is only sent that
    page's updates. Without it, it is sent every update, and so needs
    `authorize` to pass.
    """
    if not is_same_origin(request):
        raise web.HTTPForbidden(text="Another site's page can't open this socket.")

    page = request.query.get("page")
    allowed = (
        await can_see_page(request, page) if page else await is_authorized(request)
    )

    if not allowed:
        raise denied(request, page=False)

    client = web.WebSocketResponse(heartbeat=HEARTBEAT)
    await client.prepare(request)

    request.app[CLIENTS][client] = page

    try:
        async for _ in client:
            # Pages only listen, anything they send is ignored.
            pass
    finally:
        request.app[CLIENTS].pop(client, None)

    return client
