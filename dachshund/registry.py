import atexit
import logging
import queue
import threading
from datetime import datetime, timezone
from typing import Any

from aiohttp import web

from dachshund.runtime.boot import DEFAULT_HOST, DEFAULT_PORT, Runtime
from dachshund.storage.events import Event, EventStore
from dachshund.widgets import CHARTS, build
from dachshund.widgets.base import Widget
from dachshund.widgets.builtin.line import LineGraph

QUEUE_SIZE = 10_000

logger = logging.getLogger("dachshund")

_dashboard: "Dashboard | None" = None

# Re-entrant, because `init()` runs registration code that takes the lock too.
_lock = threading.RLock()


class Dashboard:
    """Everything one process puts on its dashboard.

    A dashboard describes the service it watches, holds the widgets drawn on
    it, and owns the runtime serving them.

    The name is optional and never guessed from the process, which under a
    server runner would name the runner rather than your service.

    Most applications never build one directly, the module-level API works
    against a default dashboard that `dachshund.init()` starts.

    ## Example

    ```python
    dashboard = Dashboard("Ada", description="Code Society's Matrix bot")
    dashboard.graph("latency")
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
    ) -> None:
        if name is not None and not name.strip():
            raise ValueError("A dashboard name cannot be blank.")

        self.name = name
        self.description = description
        self.started_at = datetime.now(tz=timezone.utc)

        self.widgets: dict[str, Widget] = {}
        self.events = EventStore()
        self.dropped = 0

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
        """Stop serving the dashboard."""
        self.runtime.stop()

    def add(self, widget: Widget) -> Widget:
        """Put a widget on the dashboard.

        ## Example

        ```python
        dashboard.add(LineGraph("latency", source="latency"))
        ```
        """
        if widget.name in self.widgets:
            raise ValueError(f"A widget named {widget.name!r} already exists.")

        self.widgets[widget.name] = widget

        return widget

    def widget(self, name: str, *, type: str = "line", **options: Any) -> Widget:
        """Put a widget of any registered type on the dashboard.

        ## Example

        ```python
        dashboard.widget("latency", type="line", size=2)
        ```
        """
        return self.add(build(name, type=type, **options))

    def graph(
        self,
        name: str,
        *,
        chart: str = "line",
        source: str | None = None,
        field: str = "value",
        title: str | None = None,
        size: int = 1,
    ) -> Widget:
        """Put a chart of one value over time on the dashboard.

        The source defaults to the widget's own name, so emitting under that
        name is enough to feed it.

        ## Example

        ```python
        dashboard.graph("latency", size=2)
        dashboard.emit("latency", value=96)
        ```
        """
        if chart not in CHARTS:
            known = ", ".join(sorted(CHARTS))
            raise ValueError(f"A graph is charted as {known}.")

        return self.widget(
            name,
            type=CHARTS[chart].type,
            source=source or name,
            field=field,
            title=title,
            size=size,
        )

    def emit(self, source: str, /, **fields: Any) -> None:
        """Record something that happened, for the widgets watching `source`.

        The fields are the event, and each widget reads the ones it draws.
        Calling this never blocks and never raises

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
        """Move every queued event into the store, and hand them back."""
        drained = []

        while True:
            try:
                event = self._queue.get_nowait()
            except queue.Empty:
                break

            self.events.append(event)
            drained.append(event)

        return drained

    def watching(self, source: str) -> list[Widget]:
        """The widgets fed by a source."""
        return [widget for widget in self.widgets.values() if widget.source == source]

    def _create_app(self) -> web.Application:
        """Build the application that serves this dashboard."""
        from dachshund.runtime.http import create_app

        return create_app(self)


def default() -> Dashboard:
    """The dashboard the module-level API works against.

    Built on first use so widgets can be registered at import time, long
    before `init()` starts serving anything.
    """
    global _dashboard

    with _lock:
        if _dashboard is None:
            _dashboard = Dashboard()

        return _dashboard


def init(
    name: str | None = None,
    *,
    description: str | None = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> Dashboard:
    """Start the dashboard alongside your application.

    The name is what the dashboard calls your service. Both it and the
    description are optional: without a name the dashboard falls back to a
    generic title.

    Widgets registered before this call are kept, so `init()` belongs wherever
    your application starts up.

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
    dashboard = default()

    with _lock:
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


def graph(name: str, **options: Any) -> Widget:
    """Put a chart of one value over time on the default dashboard.

    ## Example

    ```python
    import dachshund

    dachshund.graph("latency", size=2)
    ```
    """
    return default().graph(name, **options)


def widget(name: str, *, type: str = "line", **options: Any) -> Widget:
    """Put a widget of any registered type on the default dashboard.

    ## Example

    ```python
    import dachshund

    dachshund.widget("latency", type="line", size=2)
    ```
    """
    return default().widget(name, type=type, **options)


def emit(source: str, /, **fields: Any) -> None:
    """Record something that happened, on the default dashboard.

    ## Example

    ```python
    import dachshund

    dachshund.emit("latency", value=96)
    ```
    """
    default().emit(source, **fields)
