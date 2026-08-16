import asyncio
import logging
from contextlib import suppress
from typing import Any, AsyncIterator

from aiohttp import WSCloseCode, web

from dachshund.registry import Dashboard
from dachshund.runtime.keys import CLIENTS, DASHBOARD
from dachshund.storage.events import Event
from dachshund.widgets.base import Widget

WS_PATH = "/_ws"
PUMP_INTERVAL = 0.2
HEARTBEAT = 30.0

logger = logging.getLogger("dachshund")


def message(widget: Widget, data: dict[str, Any]) -> dict[str, Any]:
    """Build what a page applies to one widget."""
    return {"widget": widget.name, "op": widget.op, "data": data}


async def updates(dashboard: Dashboard, events: list[Event]) -> list[dict[str, Any]]:
    """Build what the open pages need to apply for a batch of events.

    An event updates every widget watching its source, so one emit can
    update several widgets.

    ## Example

    ```python
    dashboard = Dashboard(path=":memory:")
    dashboard.chart("latency", type="timeseries")
    dashboard.emit("latency", value=96)

    events = dashboard.drain()
    await dashboard.events.append(events)
    await updates(dashboard, events)
    # [{"widget": "latency", "op": "append", "data": {"x": ..., "y": [96.0]}}]
    ```
    """
    messages = []
    rebuilt: dict[str, Widget] = {}
    persisting: dict[str, Widget] = {}

    for event in events:
        for widget in dashboard.watching(event.source):
            widget.accumulate(event)

            if getattr(widget, "persist", False):
                persisting[widget.name] = widget

            if widget.op != "append":
                rebuilt[widget.name] = widget
                continue

            change = widget.update(event)

            if change is not None:
                messages.append(message(widget, change))

    if dashboard.storage is not None:
        for widget in persisting.values():
            snapshot = widget.snapshot()

            if snapshot is None:
                continue

            try:
                await dashboard.storage.save(widget.name, snapshot)
            except Exception:
                logger.exception("Could not persist %r's state.", widget.name)

    for widget in rebuilt.values():
        kept = await dashboard.events.events(widget.source)
        messages.append(message(widget, widget.render(kept)))

    return messages


async def hydrate(dashboard: Dashboard) -> None:
    """Seed every persisting widget from whatever storage last saved for it.

    ## Example

    ```python
    await hydrate(dashboard)
    ```
    """
    if dashboard.storage is None:
        return

    for widget in dashboard.widgets.values():
        if not getattr(widget, "persist", False):
            continue

        try:
            data = await dashboard.storage.load(widget.name)
        except Exception:
            logger.exception("Could not load %r's persisted state.", widget.name)
            continue

        if data is not None:
            widget.restore(data)


async def broadcast(app: web.Application, messages: list[dict[str, Any]]) -> None:
    """Push a batch of updates to every open page.

    Pages that have gone away are dropped rather than retried.
    """
    if not messages:
        return

    clients = app[CLIENTS]

    for client in list(clients):
        try:
            await client.send_json(messages)
        except (ConnectionResetError, RuntimeError):
            clients.discard(client)


async def pump(app: web.Application) -> None:
    """Move emitted events into the store and out to the open pages.

    This is the only place the store is written, so it needs no locking. It
    always runs on the runtime's event loop.

    ## Example

    ```python
    asyncio.create_task(pump(app))
    ```
    """
    dashboard = app[DASHBOARD]

    while True:
        await asyncio.sleep(PUMP_INTERVAL)

        try:
            events = dashboard.drain()
            await dashboard.events.append(events)
            await dashboard.events.compact()
            await broadcast(app, await updates(dashboard, events))
        except Exception:
            logger.exception("Dropped a batch of dashboard updates.")


async def pumping(app: web.Application) -> AsyncIterator[None]:
    """Run the pump for as long as the application is served.

    Persisting widgets are hydrated first, before the site accepts any
    connections, so the very first page load already reflects them.
    """
    await hydrate(app[DASHBOARD])

    task = asyncio.create_task(pump(app))

    yield

    task.cancel()

    with suppress(asyncio.CancelledError):
        await task

    clients = app[CLIENTS]

    for client in list(clients):
        await client.close(code=WSCloseCode.GOING_AWAY, message=b"shutting down")


async def websocket(request: web.Request) -> web.WebSocketResponse:
    """Hold a page's connection open for as long as it is looking."""
    client = web.WebSocketResponse(heartbeat=HEARTBEAT)
    await client.prepare(request)

    request.app[CLIENTS].add(client)

    try:
        async for _ in client:
            pass  # Pages only listen, anything they send is ignored.
    finally:
        request.app[CLIENTS].discard(client)

    return client
