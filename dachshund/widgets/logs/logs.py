import asyncio
import logging
import threading
from dataclasses import KW_ONLY, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Sequence

from dachshund.runtime.boot import RUNTIME_THREAD
from dachshund.storage.events import Event
from dachshund.widgets.query import TableQuery
from dachshund.widgets.table.table import Table

if TYPE_CHECKING:
    from dachshund.registry import Dashboard

LEVELS = logging.getLevelNamesMapping()
SHOWN = (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL)
FORMATTER = logging.Formatter()

SERVER_LOGGER = "aiohttp"

logger = logging.getLogger("dachshund")

_emitting = threading.local()


def _within(name: str, parent: str) -> bool:
    """Whether logger `name` is `parent` or one of its children."""
    return parent == "" or name == parent or name.startswith(f"{parent}.")


class LogsHandler(logging.Handler):
    """Turns a `Logs` widget's log records into events of its source."""

    def __init__(self, widget: "Logs", dashboard: "Dashboard") -> None:
        super().__init__(widget.levelno)
        self.widget = widget
        self.dashboard = dashboard

    def skips(self, record: logging.LogRecord) -> bool:
        """Whether `record` stays out of the widget."""
        if getattr(_emitting, "active", False):
            return True

        if any(_within(record.name, name) for name in self.widget.exclude):
            return True

        return threading.current_thread().name == RUNTIME_THREAD and _within(
            record.name, SERVER_LOGGER
        )

    def emit(self, record: logging.LogRecord) -> None:
        if self.skips(record):
            return

        try:
            message = record.getMessage()
        except Exception:
            self.handleError(record)
            return

        _emitting.active = True

        try:
            self.dashboard.emit(
                self.widget.source,
                time=record.created,
                level=record.levelname,
                levelno=record.levelno,
                logger=record.name,
                message=message,
                _exception=(
                    FORMATTER.formatException(record.exc_info)
                    if record.exc_info
                    else None
                ),
            )
        finally:
            _emitting.active = False


@dataclass
class Logs(Table):
    """The application's Python logs, newest first, live.

    Adding the widget attaches a handler to its `include` loggers, removed
    when the widget leaves the dashboard or the dashboard stops. Lines are
    events of its source, and the newest `keep` stay in the event store,
    across restarts.

    ## Example

    ```python
    with dachshund.row():
        dachshund.add(Logs("logs"))
        dachshund.add(Logs("api_errors", include=["myapp.api"], level="ERROR"))
        dachshund.add(Logs("quiet", exclude=["apscheduler", "httpx"]))
    ```

    ## Options

    - `include` (`list[str]`) - Loggers captured, with their children.
      Defaults to every logger.
    - `exclude` (`list[str]`) - Loggers left out, with their children, each
      under an included one. Defaults to none.
    - `level` (`str`) - The lowest level captured, like `"WARNING"`. Defaults
      to `"INFO"`.
    - `keep` (`int`) - Lines kept. Defaults to `500`.
    - `page_size` (`int`) - Lines per page. Defaults to `50`.
    - `search` (`bool`) - Shows a search box. Defaults to `True`.
    """

    _: KW_ONLY

    include: list[str] = field(default_factory=list)
    level: str = "INFO"
    exclude: list[str] = field(default_factory=list)
    keep: int = 500
    columns: list[str] = field(
        default_factory=lambda: ["time", "level", "logger", "message"]
    )
    page_size: int = 50
    sortable: list[str] | None = field(default_factory=list)

    handler: LogsHandler | None = field(
        default=None, init=False, repr=False, compare=False
    )

    type: ClassVar[str] = "logs"
    script: ClassVar[Path] = Path(__file__).parent / "logs.js"
    style: ClassVar[Path] = Path(__file__).parent / "logs.css"

    def __post_init__(self) -> None:
        if self.persist:
            raise ValueError(
                f"{self.name!r} keeps its lines in the event store, give it "
                "`keep` instead of persist=True."
            )

        super().__post_init__()

        if self.level not in LEVELS:
            raise ValueError(
                f"{self.name!r} has level={self.level!r}, use one of "
                f"{', '.join(sorted(LEVELS, key=LEVELS.__getitem__))}."
            )

        if self.keep < 1:
            raise ValueError(f"{self.name!r} has keep={self.keep}, keep at least 1.")

        if self.include:
            stray = [
                name
                for name in self.exclude
                if not any(
                    name != parent and _within(name, parent) for parent in self.include
                )
            ]

            if stray:
                raise ValueError(
                    f"{self.name!r} excludes {', '.join(stray)}, outside what it "
                    "includes. Exclude only loggers under an included one."
                )

    def raw_events(self) -> int | None:
        """Its newest `keep` lines."""
        return self.keep

    @property
    def levelno(self) -> int:
        return LEVELS[self.level]

    def captured(self) -> list[logging.Logger]:
        """The loggers its handler attaches to."""
        names = set(self.include) or {""}

        return [
            logging.getLogger(name or None)
            for name in sorted(names)
            if not any(other != name and _within(name, other) for other in names)
        ]

    def bind(self, dashboard: "Dashboard") -> None:
        """Attach this widget's handler to its loggers."""
        if self.handler is not None:
            return

        self.handler = LogsHandler(self, dashboard)

        for captured in self.captured():
            captured.addHandler(self.handler)

            if captured.getEffectiveLevel() > self.levelno:
                logger.warning(
                    "%r shows %s and up, but its logger %r only passes %s and up. "
                    "Lower the logger's level to see those lines.",
                    self.name,
                    self.level,
                    captured.name,
                    logging.getLevelName(captured.getEffectiveLevel()),
                )

    def unbind(self) -> None:
        """Detach this widget's handler from its loggers."""
        if self.handler is None:
            return

        for captured in self.captured():
            captured.removeHandler(self.handler)

        self.handler = None

    def render(self, events: Sequence[Event]) -> dict[str, Any]:
        """Every kept line, newest first."""
        payload = super().render(events)
        payload["rows"].reverse()

        return payload

    async def page(
        self,
        events: Sequence[Event],
        query: TableQuery,
        context: object,
        host_loop: asyncio.AbstractEventLoop | None = None,
    ) -> dict[str, Any]:
        """A page of lines, with the levels offered and the ones shown.

        `levels` are the toggles drawn, the levels this widget captures.
        `shown` are the ones picked, empty meaning all of them.
        """
        payload = await super().page(events, query, context, host_loop)
        payload["levels"] = [level for level in SHOWN if level >= self.levelno]
        payload["shown"] = sorted(query.levels)

        return payload

    def query(
        self, rows: list[dict[str, Any]], query: TableQuery
    ) -> list[dict[str, Any]]:
        """`rows` at one of `query`'s levels, all of them when it names none, matching its search."""
        if query.levels:
            rows = [row for row in rows if row["fields"].get("levelno") in query.levels]

        return super().query(rows, query)
