import asyncio
import atexit
import logging
import queue
import threading
from contextlib import AbstractContextManager, suppress
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable, Mapping
from zoneinfo import ZoneInfo

from aiohttp import web

from dachshund.actions import Action, Context, make_action
from dachshund.layout import DEFAULT_PAGE, Builder, Column, Page, Row
from dachshund.runtime.boot import DEFAULT_HOST, DEFAULT_PORT, Runtime
from dachshund.storage import db
from dachshund.storage.events import MIGRATIONS as EVENTS_MIGRATIONS
from dachshund.storage.events import DEFAULT_PATH, Event, EventStore
from dachshund.storage.protocol import Storage
from dachshund.widgets.base import Widget
from dachshund.widgets.persistable import persisting

QUEUE_SIZE = 10_000

logger = logging.getLogger("dachshund")

Authorize = Callable[[web.Request], bool | Awaitable[bool]]
Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
LOGIN_PREFIX = "/_auth"

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
    with dashboard.row():
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
    - `authorize` (`Callable`) - Called with a request for anything that
      isn't `public`, sync or async, returning whether to let it in. See
      [Authentication](../guides/authentication.md). Defaults to `None`,
      everything is public.
    - `login_url` (`str`) - Where a denied page redirects, with the page's URL
      as `next`. Defaults to `None`, a denied page asks for a password.
    - `login` (`dict`) - Login handlers served by the dashboard, for an
      application with no web server of its own: aiohttp handlers by name,
      each at `/_auth/<name>`, public. A denied page redirects to
      `/_auth/login`, so `"login"` is required. Can't be combined with
      `login_url`. Defaults to `None`.
    - `timezone` (`str`) - The IANA zone, like `"America/Toronto"`, where
      `"day"`, `"week"` and `"month"` windows and daily buckets start. See
      [Aggregating](../guides/widgets.md#aggregating). Defaults to `"UTC"`.
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
        authorize: Authorize | None = None,
        login_url: str | None = None,
        login: Mapping[str, Handler] | None = None,
        timezone: str = "UTC",
    ) -> None:
        if name is not None and not name.strip():
            raise ValueError("A dashboard name cannot be blank.")

        self.name = name
        self.description = description
        self.started_at = datetime.now(tz=UTC)
        self.path = path

        self.widgets: dict[str, Widget] = {}
        self.actions: dict[str, Action] = {}
        self.pages: dict[str, Page] = {}
        self.placements: dict[str, str] = {}
        self._builders: dict[str, Builder] = {}
        self.dropped = 0
        self._dropping = False

        self._connection, self._executor = db.setup(path, EVENTS_MIGRATIONS)
        self.events = EventStore(self._connection, self._executor)

        # No default: a persisting widget's state is a deliberate choice,
        # not something to quietly tuck into the same file as raw events.
        self.storage = storage
        self.context: Context = dict(context) if context else {}
        self.authorize = authorize
        self.login_url: str | None = None
        self.login: dict[str, Handler] = {}
        self.timezone = ZoneInfo(timezone)

        self.runtime = Runtime(self._create_app, host=host, port=port)
        self.set_login(login_url, login)
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

        for widget in self.widgets.values():
            widget.bind(self)

        self.runtime.start()

    def stop(self) -> None:
        """Stop serving the dashboard. `start()` serves it again."""
        self.runtime.stop()

        for widget in self.widgets.values():
            widget.unbind()

    def close(self) -> None:
        """Stop serving and close the raw events file.

        The dashboard can't be started again. `storage` is left open.
        """
        self.stop()
        self.events.close()

    def action(
        self,
        name: str,
        *,
        label: str | None = None,
        confirm: bool = False,
        public: bool = False,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register an action, called from a button on the dashboard.

        The handler's first parameter must be `ctx`, it receives the dashboard's
        `context`. See [Actions](../guides/actions.md).

        ## Example

        ```python
        @dashboard.action("block_user", label="Block", confirm=True)
        def block_user(ctx, user_id: str) -> None: ...
        ```

        ## Options

        - `name` (`str`) - The name widgets list in `actions`. Required.
        - `label` (`str`) - The button's text. Defaults to `name`.
        - `confirm` (`bool`) - Asks before running. Defaults to `False`.
        - `public` (`bool`) - Runs without the dashboard's `authorize`, see
          [Authentication](../guides/authentication.md). Defaults to `False`.
        """

        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            if name in self.actions:
                raise ValueError(f"An action named {name!r} already exists.")

            self.actions[name] = make_action(
                name, handler, label=label, confirm=confirm, public=public
            )
            return handler

        return decorator

    @property
    def login_page(self) -> str | None:
        """Where a denied page redirects: `login_url`, or the `login` handler."""
        return f"{LOGIN_PREFIX}/login" if self.login else self.login_url

    def set_login(
        self, login_url: str | None, login: Mapping[str, Handler] | None
    ) -> None:
        """Set where visitors log in: an application's page, or handlers served here."""
        if login_url is not None and login:
            raise ValueError(
                "Give `login_url` or `login`, not both: there's one place to log in."
            )

        if login:
            if "login" not in login:
                raise ValueError(
                    "`login` needs a 'login' handler, where denied pages redirect."
                )

            for name in login:
                if not name or "/" in name:
                    raise ValueError(
                        f"Login handler names are one path segment, got {name!r}."
                    )

            if self.is_running:
                raise RuntimeError("Give `login` before the dashboard starts.")

            self.login, self.login_url = dict(login), None
        elif login_url is not None:
            self.login_url, self.login = login_url, {}

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
        with page.row():
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
                self._register(widget, each.path)

            self.actions.update(each.actions)
            each.included = True

        return page

    def page(
        self, name: str, *, title: str | None = None, public: bool | None = None
    ) -> Page:
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
        - `public` (`bool`) - Shown without the dashboard's `authorize`, see
          [Authentication](../guides/authentication.md). Defaults to `False`.
        """
        existing = self.pages.get(name)

        if existing is None:
            return self.include(Page(name, title=title, public=bool(public)))

        if title is not None:
            existing.title = title

        if public is not None:
            existing.public = public

        return existing

    def row(self, *, page: str = DEFAULT_PAGE) -> AbstractContextManager[Row]:
        """Open a row on `page`, see [Page.row][dachshund.layout.Page.row].

        ## Example

        ```python
        with dashboard.row():
            dashboard.add(Number("errors"))
            dashboard.add(TimeSeriesChart("latency"))
        ```
        """
        return self._builder(page).row()

    def column(
        self, *, span: int | None = None, page: str = DEFAULT_PAGE
    ) -> AbstractContextManager[Column]:
        """Open a column inside a row on `page`, see [Page.column][dachshund.layout.Page.column]."""
        return self._builder(page).column(span)

    def add(self, widget: Widget, *, page: str = DEFAULT_PAGE) -> None:
        """Put a widget in the row or column open on `page`.

        See [Page.add][dachshund.layout.Page.add].

        ## Options

        - `page` (`str`) - The page it goes on. Defaults to `"default"`.
        """
        self._builder(page).add(widget)

    def widget_page(self, name: str, default: str = DEFAULT_PAGE) -> str:
        """The page a widget appears on."""
        return self.placements.get(name, default)

    def layout(self, page: str = DEFAULT_PAGE) -> list[Row]:
        """`page`'s rows, in display order.

        ## Example

        ```python
        dashboard.layout("requests")
        # [Row([Column(["errors", "users"], span=4), Column(["latency"])])]
        ```
        """
        declared = self.pages.get(page)

        return list(declared.rows) if declared else []

    def _check_storage(self, widget: Widget) -> None:
        if persisting(widget) and self.storage is None:
            raise ValueError(
                f"{widget.name!r} wants to persist, but no storage is "
                "configured. Pass storage=... to Dashboard() or "
                "dachshund.init()."
            )

    def _register(self, widget: Widget, page: str | None) -> None:
        if widget.name in self.widgets:
            raise ValueError(f"A widget named {widget.name!r} already exists.")

        self._check_storage(widget)

        if page is not None and self.page(page).tabs:
            raise ValueError(f"Page {page!r} has tabs, put widgets on one.")

        self.widgets[widget.name] = widget
        widget.bind(self)

        if page is not None:
            self.placements[widget.name] = page

    def _unregister(self, name: str) -> None:
        widget = self.widgets.pop(name, None)
        self.placements.pop(name, None)

        if widget is not None:
            widget.unbind()

    def _builder(self, page: str) -> Builder:
        target = self.page(page)

        if target.path not in self._builders:
            self._builders[target.path] = Builder(
                target,
                lambda on, widget: self._register(widget, on.path),
                lambda on, name: self._unregister(name),
            )

        return self._builders[target.path]

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
    authorize: Authorize | None = None,
    login_url: str | None = None,
    login: Mapping[str, Handler] | None = None,
    timezone: str | None = None,
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

        if authorize is not None:
            dashboard.authorize = authorize

        dashboard.set_login(login_url, login)

        if timezone is not None:
            dashboard.timezone = ZoneInfo(timezone)

        if host not in LOCAL_HOSTS and dashboard.authorize is None:
            logger.warning(
                "The dashboard listens on %s with no `authorize`: anyone who "
                "can reach it sees every page and runs every action.",
                host,
            )

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
    def block_user(ctx: dachshund.Context, user_id: str) -> None: ...
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


def row(**options: Any) -> AbstractContextManager[Row]:
    """Open a row, on the default dashboard.

    Takes what [Dashboard.row][dachshund.registry.Dashboard.row] does.

    ## Example

    ```python
    import dachshund
    from dachshund.widgets import Number, TimeSeriesChart

    with dachshund.row():
        dachshund.add(Number("errors"))
        dachshund.add(TimeSeriesChart("latency"))
    ```
    """
    return default().row(**options)


def column(**options: Any) -> AbstractContextManager[Column]:
    """Open a column inside a row, on the default dashboard.

    Takes what [Dashboard.column][dachshund.registry.Dashboard.column] does.
    """
    return default().column(**options)


def add(widget: Widget, **options: Any) -> None:
    """Put a widget in the open row or column, on the default dashboard.

    Takes what [Dashboard.add][dachshund.registry.Dashboard.add] does.

    ## Example

    ```python
    import dachshund
    from dachshund.widgets import Number

    with dachshund.row():
        dachshund.add(Number("errors"))
    ```
    """
    default().add(widget, **options)


def _repeated(names: list[str]) -> list[str]:
    return sorted({name for name in names if names.count(name) > 1})
