import atexit
import logging
import queue
import threading
from datetime import datetime, timezone
from typing import Any, Sequence

from aiohttp import web

from dachshund.runtime.boot import DEFAULT_HOST, DEFAULT_PORT, Runtime
from dachshund.storage import db
from dachshund.storage.events import MIGRATIONS as EVENTS_MIGRATIONS
from dachshund.storage.events import DEFAULT_PATH, Event, EventStore
from dachshund.storage.protocol import Storage
from dachshund.widgets import build
from dachshund.widgets.base import Widget

QUEUE_SIZE = 10_000

logger = logging.getLogger("dachshund")

_dashboard: "Dashboard | None" = None

# Re-entrant, because `init()` runs registration code that takes the lock too.
_lock = threading.RLock()


class Dashboard:
    """Everything one process puts on its dashboard.

    A dashboard describes the service it watches, holds the widgets drawn on
    it, and owns the runtime serving them.

    Most applications never build one directly, the module-level API works
    with a default dashboard that `dachshund.init()` starts.

    ## Example

    ```python
    dashboard = Dashboard("Ada", description="Code Society's Matrix bot")
    dashboard.chart("latency", type="timeseries")
    dashboard.start()
    ```
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
    ) -> None:
        if name is not None and not name.strip():
            raise ValueError("A dashboard name cannot be blank.")

        self.name = name
        self.description = description
        self.started_at = datetime.now(tz=timezone.utc)
        self.path = path

        self.widgets: dict[str, Widget] = {}
        self.dropped = 0

        self._connection, self._executor = db.setup(path, EVENTS_MIGRATIONS)
        self.events = EventStore(self._connection, self._executor)

        # No default: a persisting widget's state is a deliberate choice,
        # not something to quietly tuck into the same file as raw events.
        self.storage = storage

        self.runtime = Runtime(self._create_app, host=host, port=port)
        self._queue: queue.Queue[Event] = queue.Queue(maxsize=QUEUE_SIZE)

    @property
    def url(self) -> str:
        """The address the dashboard is reachable at."""
        return self.runtime.url

    @property
    def is_running(self) -> bool:
        """Whether the dashboard is being served."""
        return self.runtime.is_running

    def start(self) -> None:
        """Serve the dashboard."""
        self.runtime.start()

    def stop(self) -> None:
        """Stop serving the dashboard.

        The dashboard itself is untouched, `start()` again later picks up
        right where it left off. For releasing it for good, see `close()`.
        """
        self.runtime.stop()

    def close(self) -> None:
        """Stop serving and release the connection backing raw events.

        Unlike `stop()`, this dashboard can't be started again afterward.
        A `storage=...` you configured is yours, this never closes it,
        Dashboard didn't create it.
        """
        self.stop()
        self.events.close()

    def add(self, widget: Widget) -> Widget:
        """Add a widget on the dashboard.

        ## Example

        ```python
        dashboard.add(TimeSeriesChart("latency", source="latency"))
        ```
        """
        if widget.name in self.widgets:
            raise ValueError(f"A widget named {widget.name!r} already exists.")

        if getattr(widget, "persist", False):
            if self.storage is None:
                raise ValueError(
                    f"{widget.name!r} wants to persist, but no storage is "
                    "configured. Pass storage=... to Dashboard() or "
                    "dachshund.init()."
                )

            if self.is_running:
                logger.warning(
                    "%r was registered after the dashboard started, so its "
                    "persisted state was never restored. Register persisting "
                    "widgets before calling start()/dachshund.init(), not "
                    "after, or their history is silently lost on every restart.",
                    widget.name,
                )

        self.widgets[widget.name] = widget

        return widget

    def widget(self, name: str, *, type: str = "line", **options: Any) -> Widget:
        """Add a widget of any registered type on the dashboard.

        ## Example

        ```python
        dashboard.widget("latency", type="timeseries", size=2)
        ```
        """
        return self.add(build(name, type=type, **options))

    def chart(
        self,
        name: str,
        *,
        type: str = "line",
        source: str | None = None,
        x: str | None = None,
        y: str | Sequence[str] = "value",
        title: str | None = None,
        size: int = 1,
        persist: bool = False,
    ) -> Widget:
        """Add a chart on the dashboard.

        The type decides what is drawn and how `x` and `y` are read:

        - `timeseries`: [TimeSeriesChart][dachshund.TimeSeriesChart], a line
          over the time each event was emitted.
        - `line`: [LineChart][dachshund.LineChart], one value against
          another.
        - `bar`: [BarChart][dachshund.BarChart], a total per category.

        `y` names the field drawn and defaults to `value`.

        The source defaults to the chart's own name, so emitting under that
        name is enough to feed it. `title` names the card and `size` is how
        many of the three columns it spans.

        `persist` is [BarChart][dachshund.BarChart]'s own opt-in, forwarded
        here since `bar` is one of the types this method knows about: its
        totals survive a restart instead of only covering the events
        currently kept. It needs `storage=...` configured on the dashboard
        first (see [Dashboard][dachshund.Dashboard]), nothing persists by
        default. Persisting isn't bar-chart-specific though: any widget can
        keep its own state the same way, see [Widget][dachshund.Widget].

        ## Example

        ```python
        dashboard.chart("latency", type="timeseries", title="Response time", size=2)
        dashboard.emit("latency", value=96)
        ```

        ```python
        from dachshund.storage.sqlite import SQLiteStorage

        dashboard = Dashboard(storage=SQLiteStorage("widget_state.db"))
        dashboard.chart("commands", type="bar", x="name", persist=True)
        dashboard.emit("commands", name="/ban", value=1)
        ```
        """
        options: dict[str, Any] = {"y": y}

        if x is not None:
            options["x"] = x

        if persist:
            options["persist"] = True

        return self.widget(
            name,
            type=type,
            source=source or name,
            title=title,
            size=size,
            **options,
        )

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
        except queue.Full:
            self.dropped += 1

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

    def _create_app(self) -> web.Application:
        """Build the application that serves this dashboard."""
        from dachshund.runtime.http import create_app

        return create_app(self)


def default(*, path: str = DEFAULT_PATH, storage: Storage | None = None) -> Dashboard:
    """The dashboard the module-level API works with.

    Built on first use so widgets can be registered at import time, long
    before `init()` starts. `path` and `storage` only matter on that first
    use: storage is opened once, at construction, and can't be re-pointed
    afterward.
    """
    global _dashboard

    with _lock:
        if _dashboard is None:
            _dashboard = Dashboard(path=path, storage=storage)

        return _dashboard


def init(
    name: str | None = None,
    *,
    description: str | None = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    path: str = DEFAULT_PATH,
    storage: Storage | None = None,
) -> Dashboard:
    """Start the dashboard alongside your application.

    `name` and `description` appear at the top of the dashboard page. Leave
    `name` unset and the dashboard falls back to a generic title; leave
    `description` unset and none is shown. Widgets registered before this
    call are kept.

    ## Example

    ```python
    import dachshund

    dachshund.init("Ada", description="Code Society's Matrix bot")
    ```

    Bind to all interfaces to expose the dashboard beyond the local machine:

    ```python
    dachshund.init("Ada", host="0.0.0.0", port=1212)
    ```
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

        dashboard.runtime.host = host
        dashboard.runtime.requested_port = port
        dashboard.start()

        atexit.unregister(dashboard.stop)
        atexit.register(dashboard.stop)

        return dashboard


def shutdown() -> None:
    """Stop the dashboard started by `init()`.

    The widgets registered on it are kept, so it can be started again.
    """
    with _lock:
        if _dashboard is None:
            return

        _dashboard.stop()
        atexit.unregister(_dashboard.stop)


def chart(name: str, **options: Any) -> Widget:
    """Put a chart on the default dashboard.

    Takes what [Dashboard.chart][dachshund.registry.Dashboard.chart] does.

    ## Example

    ```python
    import dachshund

    dachshund.chart("latency", type="timeseries", size=2)
    ```
    """
    return default().chart(name, **options)


def widget(name: str, *, type: str = "line", **options: Any) -> Widget:
    """Put a widget of any registered type on the default dashboard.

    ## Example

    ```python
    import dachshund

    dachshund.widget("latency", type="timeseries", size=2)
    ```
    """
    return default().widget(name, type=type, **options)


def emit(source: str, /, **fields: Any) -> None:
    """Emit an event, on the default dashboard.

    ## Example

    ```python
    import dachshund

    dachshund.emit("latency", value=96)
    ```
    """
    default().emit(source, **fields)
