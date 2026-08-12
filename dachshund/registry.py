import atexit
import logging
import threading
from datetime import datetime, timezone

from aiohttp import web

from dachshund.runtime.boot import DEFAULT_HOST, DEFAULT_PORT, Runtime
from dachshund.runtime.http import create_app

logger = logging.getLogger("dachshund")

_dashboard: "Dashboard | None" = None
_lock = threading.RLock()


class Dashboard:
    """Everything one process puts on its dashboard.

    A dashboard describes the service it watches and owns the runtime serving
    it. Widgets, actions and pages register against it once they exist.

    Most applications never build one directly, `dachshund.init()` makes a
    default one and the module-level API works against that.

    ## Example

    ```python
    dashboard = Dashboard("Ada", description="Code Society's Matrix bot")
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
        self.runtime = Runtime(self._create_app, host=host, port=port)

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

    def _create_app(self) -> web.Application:
        """Build the application that serves this dashboard."""
        return create_app(
            name=self.name,
            description=self.description,
            started_at=self.started_at,
        )


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

    If called while the dashboard is running, it returns the same dashboard.

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
    global _dashboard

    with _lock:
        if _dashboard is not None and _dashboard.is_running:
            runtime = _dashboard.runtime

            if (runtime.host, runtime.requested_port) != (host, port):
                logger.warning(
                    "The dashboard is already running on %s, ignoring the "
                    "requested %s:%s. Call `dachshund.shutdown()` first to "
                    "rebind it.",
                    _dashboard.url,
                    host,
                    port,
                )
            return _dashboard

        if _dashboard is not None:
            atexit.unregister(_dashboard.stop)

        dashboard = Dashboard(
            name,
            description=description,
            host=host,
            port=port,
        )
        dashboard.start()

        atexit.register(dashboard.stop)
        _dashboard = dashboard

        return dashboard


def shutdown() -> None:
    """Stop the dashboard started by `init()`."""
    global _dashboard

    with _lock:
        if _dashboard is None:
            return

        _dashboard.stop()
        atexit.unregister(_dashboard.stop)
        _dashboard = None
