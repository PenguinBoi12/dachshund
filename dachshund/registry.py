import asyncio
import atexit
import logging
import queue
import threading
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from aiohttp import web

from dachshund.actions import Action, Context, make_action
from dachshund.layout import (
    DEFAULT_PAGE,
    Column,
    Page,
    Row,
    W,
    build_row,
    names_of,
    row_names,
)
from dachshund.runtime.boot import DEFAULT_HOST, DEFAULT_PORT, Runtime
from dachshund.storage import db
from dachshund.storage.events import MIGRATIONS as EVENTS_MIGRATIONS
from dachshund.storage.events import DEFAULT_PATH, Event, EventStore
from dachshund.storage.protocol import Storage
from dachshund.widgets.base import Widget
from dachshund.widgets.persistable import persisting

QUEUE_SIZE = 10_000

logger = logging.getLogger("dachshund")

_dashboard: "Dashboard | None" = None

# Re-entrant, because `init()` runs registration code that takes the lock too.
_lock = threading.RLock()


class Dashboard:
    """Everything one process shows on its dashboard: pages, widgets, actions,
    and the server drawing them.

    Most applications use the module-level API instead, which works on a
    default dashboard started by `dachshund.init()`.

    ## Example

    ```python
    dashboard = Dashboard("Ada", description="Code Society's Matrix bot")
    dashboard.add(TimeSeriesChart("latency"))
    dashboard.start()
    ```

    ## Options

    - `name` (`str`) - Shown at the top of every page. Defaults to
      `"Dashboard"`.
    - `description` (`str`) - Shown under the name. Defaults to `None`.
    - `host` (`str`) - The interface served on. Defaults to `"127.0.0.1"`,
      `"0.0.0.0"` serves every interface.
    - `port` (`int`) - The port served on. Defaults to `1212`.
    - `path` (`str`) - The SQLite file keeping raw events. Defaults to
      `"dachshund.db"`.
    - `storage` (`Storage`) - Where persisted widget state is saved, see
      [Storage](../reference/storage.md). Defaults to `None`.
    - `context` (`dict`) - Passed as `ctx` to every action and table loader.
      Defaults to `{}`.
    """

    def __init__(
        self,
        name: str | None = None,
        *,
        description: str | None = None,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        path: str = DEFAULT_PATH,
        storage: Storage | None = None,
        context: Context | None = None,
    ) -> None:
        if name is not None and not name.strip():
            raise ValueError("A dashboard name cannot be blank.")

        self.name = name
        self.description = description
        self.started_at = datetime.now(tz=timezone.utc)
        self.path = path

        self.widgets: dict[str, Widget] = {}
        self.actions: dict[str, Action] = {}
        self.pages: dict[str, Page] = {}
        self.placements: dict[str, str] = {}
        self.dropped = 0
        self._dropping = False

        self._connection, self._executor = db.setup(path, EVENTS_MIGRATIONS)
        self.events = EventStore(self._connection, self._executor)

        # No default: a persisting widget's state is a deliberate choice,
        # not something to quietly tuck into the same file as raw events.
        self.storage = storage
        self.context: Context = dict(context) if context else {}

        self.runtime = Runtime(self._create_app, host=host, port=port)
        self._queue: queue.Queue[Event] = queue.Queue(maxsize=QUEUE_SIZE)

        self.host_loop: asyncio.AbstractEventLoop | None = None

    @property
    def url(self) -> str:
        """The address the dashboard is reachable at."""
        return self.runtime.url

    @property
    def is_running(self) -> bool:
        """Whether the dashboard is being served."""
        return self.runtime.is_running

    def start(self) -> None:
        """Serve the dashboard.

        Called from a running event loop, that loop becomes `host_loop` and async
        action handlers run on it.
        """
        with suppress(RuntimeError):
            self.host_loop = asyncio.get_running_loop()

        self.runtime.start()

    def stop(self) -> None:
        """Stop serving the dashboard. `start()` serves it again."""
        self.runtime.stop()

    def close(self) -> None:
        """Stop serving and close the raw events file.

        The dashboard can't be started again. `storage` is left open.
        """
        self.stop()
        self.events.close()

    def add(self, widget: W, *, page: str | None = None) -> W:
        """Add a widget and return it.

        ## Example

        ```python
        latency = dashboard.add(TimeSeriesChart("latency"))
        dashboard.add(Number("errors"), page="errors")
        ```

        ## Options

        - `page` (`str`) - The page it goes on, declared if new. Defaults to
          `"default"`.
        """
        if widget.name in self.widgets:
            raise ValueError(f"A widget named {widget.name!r} already exists.")

        self._check_storage(widget)

        target = self.page(page) if page is not None else None

        if target is not None and target.tabs:
            raise ValueError(f"Page {page!r} has tabs, add widgets to one.")

        self.widgets[widget.name] = widget

        if page is not None:
            self.placements[widget.name] = page

        return widget

    def action(
        self, name: str, *, label: str | None = None, confirm: bool = False
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register an action, called from a button on the dashboard.

        The handler's first parameter must be `ctx`, it receives the dashboard's
        `context`. See [Actions](../reference/actions.md).

        ## Example

        ```python
        @dashboard.action("block_user", label="Block", confirm=True)
        def block_user(ctx, user_id: str) -> None: ...
        ```

        ## Options

        - `name` (`str`) - The name widgets list in `actions`. Required.
        - `label` (`str`) - The button's text. Defaults to `name`.
        - `confirm` (`bool`) - Asks before running. Defaults to `False`.
        """

        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            if name in self.actions:
                raise ValueError(f"An action named {name!r} already exists.")

            self.actions[name] = make_action(
                name, handler, label=label, confirm=confirm
            )
            return handler

        return decorator

    def emit(self, source: str, /, **fields: Any) -> None:
        """Emit an event on the dashboard.

        ## Example

        ```python
        dashboard.emit("latency", value=96)
        dashboard.emit("command", name="/ban", issuer="tomcat")
        ```
        """
        event = Event(source=source, payload=fields)

        try:
            self._queue.put_nowait(event)
            self._dropping = False
        except queue.Full:
            self.dropped += 1

            if not self._dropping:
                self._dropping = True
                logger.warning(
                    "The event queue is full (%d slots), dropping events until "
                    "it drains. %d dropped so far.",
                    QUEUE_SIZE,
                    self.dropped,
                )

    def drain(self) -> list[Event]:
        """Pull every queued event off the queue, oldest first.

        Draining alone doesn't persist anything; the caller decides when to
        `await self.events.append(...)` the batch.
        """
        drained = []

        while True:
            try:
                event = self._queue.get_nowait()
            except queue.Empty:
                break

            drained.append(event)

        return drained

    def watching(self, source: str) -> list[Widget]:
        """The widgets watching `source`."""
        return [widget for widget in self.widgets.values() if widget.source == source]

    def include(self, page: Page) -> Page:
        """Put a page, with its tabs, widgets and actions, on the dashboard.

        Nothing is added if a name is already taken. Including a page the dashboard
        already holds does nothing. An included page can't be registered on.

        ## Example

        ```python
        page = Page("errors", title="Errors")
        page.add(BarChart("errors", x="code"))
        dashboard.include(page)
        ```
        """
        if page.parent is not None:
            raise ValueError(f"{page.path!r} is a tab, include its page instead.")

        if self.pages.get(page.path) is page:
            return page

        pages = page.every()
        widgets = [name for each in pages for name in each.widgets]
        actions = [name for each in pages for name in each.actions]

        clashes = [each.path for each in pages if each.path in self.pages]
        clashes += [name for name in widgets if name in self.widgets]
        clashes += [name for name in actions if name in self.actions]
        clashes += _repeated(widgets) + _repeated(actions)

        if clashes:
            raise ValueError(f"include() names already taken: {', '.join(clashes)}.")

        for each in pages:
            for widget in each.widgets.values():
                self._check_storage(widget)

        for each in pages:
            self.pages[each.path] = each

            for widget in each.widgets.values():
                self.add(widget, page=each.path)

            self.actions.update(each.actions)
            each.included = True

        return page

    def page(self, name: str, *, title: str | None = None) -> Page:
        """Declare a page, or retitle one already declared.

        A dashboard that declares no page shows every widget on one `"default"`
        page.

        ## Example

        ```python
        dashboard.page("errors", title="Errors")
        ```

        ## Options

        - `title` (`str`) - Shown in the navigation. Defaults to `name`,
          underscores as spaces.
        """
        existing = self.pages.get(name)

        if existing is None:
            return self.include(Page(name, title=title))

        if title is not None:
            existing.title = title

        return existing

    def column(self, *widgets: Widget | str) -> Column:
        """Stack widgets top to bottom, for use in a `row()`."""
        return Column(self._known(names_of(widgets)))

    def row(
        self,
        *items: Widget | str | Column,
        widths: Iterable[int] | None = None,
        page: str = DEFAULT_PAGE,
    ) -> None:
        """Lay widgets out side by side, in a row of their own.

        A widget on no page yet moves to `page`.

        ## Example

        ```python
        dashboard.row(latency, dashboard.column(errors, users), widths=(2, 1))
        ```

        ## Options

        - `widths` (`tuple[int, ...]`) - Each item's share of the row, see
          [Row][dachshund.Row]. Defaults to equal shares.
        - `page` (`str`) - The page the row goes on. Defaults to `"default"`.
        """
        row = build_row(items, widths)
        names = self._known(row_names(row))
        elsewhere = [name for name in names if self.widget_page(name, page) != page]

        if elsewhere:
            raise ValueError(
                f"row() names widgets on another page: {', '.join(elsewhere)}."
            )

        target = self.page(page)

        if target.tabs:
            raise ValueError(f"Page {page!r} has tabs, add rows to one.")

        target.rows.append(row)

        for name in names:
            self.placements[name] = page

    def widget_page(self, name: str, default: str = DEFAULT_PAGE) -> str:
        """The page a widget appears on."""
        return self.placements.get(name, default)

    def layout(self, page: str = DEFAULT_PAGE) -> tuple[list[Row], list[str]]:
        """`page`'s rows in display order, then the widgets in no row.

        ## Example

        ```python
        dashboard.layout("requests")
        # ([Row(["latency", Column(["errors", "users"])], (2, 1))], ["cpu"])
        ```
        """
        declared = self.pages.get(page)
        rows = list(declared.rows) if declared else []
        placed = {name for row in rows for name in row_names(row)}
        flow = [
            name
            for name in self.widgets
            if name not in placed and self.widget_page(name) == page
        ]

        return rows, flow

    def _check_storage(self, widget: Widget) -> None:
        if persisting(widget) and self.storage is None:
            raise ValueError(
                f"{widget.name!r} wants to persist, but no storage is "
                "configured. Pass storage=... to Dashboard() or "
                "dachshund.init()."
            )

    def _known(self, names: list[str]) -> list[str]:
        unknown = [name for name in names if name not in self.widgets]

        if unknown:
            raise ValueError(f"No widgets named: {', '.join(unknown)}.")

        return names

    def _create_app(self) -> web.Application:
        """Build the application that serves this dashboard."""
        from dachshund.runtime.http import create_app

        return create_app(self)


def default(*, path: str = DEFAULT_PATH, storage: Storage | None = None) -> Dashboard:
    """The dashboard the module-level API works on, created on first use.

    `path` only applies to that first call. `storage` applies to the first call
    that gives one, which may come later.
    """
    global _dashboard

    with _lock:
        if _dashboard is None:
            _dashboard = Dashboard(path=path, storage=storage)
        elif storage is not None and _dashboard.storage is None:
            _dashboard.storage = storage

        return _dashboard


def init(
    name: str | None = None,
    *,
    description: str | None = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    path: str = DEFAULT_PATH,
    storage: Storage | None = None,
    context: Context | None = None,
) -> Dashboard:
    """Start the dashboard alongside your application.

    Widgets, pages and actions registered before the call are kept. Called
    again while running, it does nothing.

    ## Example

    ```python
    import dachshund

    dachshund.init("Ada", description="Code Society's Matrix bot", context={"bot": bot})
    ```

    ## Options

    Takes the options of [Dashboard][dachshund.Dashboard]. `context` is merged
    into the context already set.
    """
    dashboard = default(path=path, storage=storage)

    with _lock:
        if dashboard.path != path:
            logger.warning(
                "The dashboard already opened %r for storage, ignoring the "
                "requested %r. Widgets registered before `init()` fix the "
                "storage path too, so pass it to the first call that "
                "touches the dashboard.",
                dashboard.path,
                path,
            )

        if storage is not None and dashboard.storage is not storage:
            logger.warning(
                "The dashboard already set up its own storage, ignoring the "
                "one requested here. Widgets registered before `init()` fix "
                "storage too, so pass it to the first call that touches the "
                "dashboard."
            )

        if dashboard.is_running:
            runtime = dashboard.runtime

            if (runtime.host, runtime.requested_port) != (host, port):
                logger.warning(
                    "The dashboard is already running on %s, ignoring the "
                    "requested %s:%s. Call `dachshund.shutdown()` first to "
                    "rebind it.",
                    dashboard.url,
                    host,
                    port,
                )
            return dashboard

        if name is not None:
            dashboard.name = name

        if description is not None:
            dashboard.description = description

        if context is not None:
            dashboard.context.update(context)

        dashboard.runtime.host = host
        dashboard.runtime.requested_port = port
        dashboard.start()

        atexit.unregister(dashboard.stop)
        atexit.register(dashboard.stop)

        return dashboard


def shutdown() -> None:
    """Stop the dashboard started by `init()`. Its widgets are kept."""
    with _lock:
        if _dashboard is None:
            return

        _dashboard.stop()
        atexit.unregister(_dashboard.stop)


def add(widget: W, *, page: str | None = None) -> W:
    """Add a widget, on the default dashboard.

    Takes what [Dashboard.add][dachshund.registry.Dashboard.add] does.

    ## Example

    ```python
    import dachshund

    dachshund.add(dachshund.TimeSeriesChart("latency"))
    ```
    """
    return default().add(widget, page=page)


def include(page: Page) -> Page:
    """Put a page on the default dashboard.

    Takes what [Dashboard.include][dachshund.registry.Dashboard.include] does.

    ## Example

    ```python
    import dachshund

    page = dachshund.Page("errors")
    dachshund.include(page)
    ```
    """
    return default().include(page)


def action(
    name: str, **kwargs: Any
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register an action, on the default dashboard.

    Takes what [Dashboard.action][dachshund.registry.Dashboard.action] does.

    ## Example

    ```python
    import dachshund

    @dachshund.action("block_user", label="Block", confirm=True)
    def block_user(ctx: dachshund.Context, user_id: str) -> None:
        ...
    ```
    """
    return default().action(name, **kwargs)


def emit(source: str, /, **fields: Any) -> None:
    """Emit an event, on the default dashboard.

    ## Example

    ```python
    import dachshund

    dachshund.emit("latency", value=96)
    ```
    """
    default().emit(source, **fields)


def page(name: str, **options: Any) -> Page:
    """Declare a page, on the default dashboard.

    Takes what [Dashboard.page][dachshund.registry.Dashboard.page] does.

    ## Example

    ```python
    import dachshund

    dachshund.page("errors", title="Errors")
    ```
    """
    return default().page(name, **options)


def column(*widgets: Widget | str) -> Column:
    """Stack widgets, on the default dashboard.

    Takes what [Dashboard.column][dachshund.registry.Dashboard.column] does.
    """
    return default().column(*widgets)


def row(*items: Widget | str | Column, **options: Any) -> None:
    """Group widgets into one row, on the default dashboard.

    Takes what [Dashboard.row][dachshund.registry.Dashboard.row] does.

    ## Example

    ```python
    import dachshund

    dachshund.row("latency", "errors", page="requests")
    ```
    """
    default().row(*items, **options)


def _repeated(names: list[str]) -> list[str]:
    return sorted({name for name in names if names.count(name) > 1})
