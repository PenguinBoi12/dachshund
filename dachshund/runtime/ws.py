import asyncio
import logging
from contextlib import suppress
from typing import Any, AsyncIterator

from aiohttp import WSCloseCode, web

from dachshund.actions import resolve_row_actions
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
        if widget.paginated:
            messages.append(message(widget, {}))
            continue

        kept = await dashboard.events.events(widget.source)
        payload = widget.render(kept)
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
        if widget.name in hydrated or not getattr(widget, "persist", False):
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

            events = dashboard.drain()
            await dashboard.events.append(events)

            skip_rollup = frozenset(
                widget.source
                for widget in dashboard.widgets.values()
                if not widget.rollup_safe
            )
            await dashboard.events.compact(skip_rollup)

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
    """Hold a page's connection open for as long as it is looking."""
    client = web.WebSocketResponse(heartbeat=HEARTBEAT)
    await client.prepare(request)

    request.app[CLIENTS].add(client)

    try:
        async for _ in client:
            # Pages only listen, anything they send is ignored.
            pass
    finally:
        request.app[CLIENTS].discard(client)

    return client
