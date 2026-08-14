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


def updates(dashboard: Dashboard, events: list[Event]) -> list[dict[str, Any]]:
    """Build what the open pages need to apply for a batch of events.

    An event updates every widget watching its source, so one emit can
    update several widgets.

    ## Example

    ```python
    dashboard = Dashboard()
    dashboard.chart("latency", type="timeseries")
    dashboard.emit("latency", value=96)

    updates(dashboard, dashboard.drain())
    # [{"widget": "latency", "op": "append", "data": {"x": ..., "y": [96.0]}}]
    ```
    """
    messages = []
    rebuilt: dict[str, Widget] = {}

    for event in events:
        for widget in dashboard.watching(event.source):
            if widget.op != "append":
                rebuilt[widget.name] = widget
                continue

            change = widget.update(event)

            if change is not None:
                messages.append(message(widget, change))

    for widget in rebuilt.values():
        kept = dashboard.events.events(widget.source)
        messages.append(message(widget, widget.render(kept)))

    return messages


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
            await broadcast(app, updates(dashboard, dashboard.drain()))
        except Exception:
            logger.exception("Dropped a batch of dashboard updates.")


async def pumping(app: web.Application) -> AsyncIterator[None]:
    """Run the pump for as long as the application is served."""
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
