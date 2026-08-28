import asyncio
import logging
from dataclasses import KW_ONLY, dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Sequence

from dachshund.actions import Context
from dachshund.storage.events import Event
from dachshund.widgets.value import numeric

MAX_SIZE = 3

logger = logging.getLogger("dachshund")

WIDGETS: dict[str, "type[Widget]"] = {}


@dataclass
class Widget:
    """A card on the dashboard, fed by an event source.

    A widget turns events into whatever its renderer draws. `render` builds the
    whole card, from every event kept for its source. `update` builds a single
    incremental change, and `op` tells the client how to apply it.

    `accumulate`, `snapshot`, and `restore` are optional, for a widget that
    wants its own state to survive a restart, backed by whatever `Storage`
    the dashboard is configured with. `persist` isn't declared here on
    `Widget` itself, each widget type that supports it declares its own, so
    building one with `persist=True` fails loudly if that type doesn't
    support it. `Table` and `BarChart` get it from
    [KeyedWidget][dachshund.widgets.state.KeyedWidget]; a widget shaped
    differently implements `accumulate`/`snapshot`/`restore` on its own
    instead.

    Subclasses pair with a renderer registered under the same `type` in the
    client's dispatch table. Set `script` (and optionally `style`) to a file
    next to the subclass's own module and dachshund serves and loads it
    automatically. The three built-in chart types work this way too; see
    `LineChart`/`BarChart`.

    `actions` names the actions a card's buttons invoke. `action_args`
    supplies static arguments by action name, e.g. `action_args={"ban":
    {"user_id": "42"}}`. Set `renders_own_actions` when a widget places its
    own buttons instead of the generic card-level row; `Table` does this,
    merging `action_args` with each row's own fields.

    `rollup_safe` opts a widget's source into `EventStore.compact`'s numeric
    averaging past `retention`; see there for why it defaults to `False`.

    `paginated` marks a widget whose rows are fetched a page at a time
    through `page()` instead of sent whole; `Table` is the built-in example.

    ## Example

    ```python
    class Gauge(Widget):
        type: ClassVar[str] = "gauge"
        script: ClassVar[Path] = Path(__file__).parent / "gauge.js"
    ```
    """

    name: str

    _: KW_ONLY

    source: str
    title: str | None = None
    size: int = 1
    actions: list[str] = field(default_factory=list)
    action_args: dict[str, dict[str, Any]] = field(default_factory=dict)

    warned: set[str] = field(
        default_factory=set,
        init=False,
        repr=False,
        compare=False,
    )

    type: ClassVar[str] = "widget"
    op: ClassVar[str] = "replace"
    script: ClassVar[Path | None] = None
    style: ClassVar[Path | None] = None
    renders_own_actions: ClassVar[bool] = False
    rollup_safe: ClassVar[bool] = False
    paginated: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        for attr in ("script", "style"):
            path = getattr(cls, attr)

            if path is not None and not Path(path).is_file():
                raise FileNotFoundError(
                    f"{cls.__name__}.{attr} points at {path}, which doesn't exist."
                )

        # A widget registers itself here, so a custom one needs nothing more
        # than a `type` of its own and being imported once.
        WIDGETS[cls.type] = cls

    def __post_init__(self) -> None:
        if not 1 <= self.size <= MAX_SIZE:
            raise ValueError(f"A widget spans 1 to {MAX_SIZE} columns.")

    def warn(self, field: str, value: Any) -> None:
        """Say a field could not be read, once, however often it arrives."""
        if field in self.warned:
            return

        self.warned.add(field)

        if value is None:
            logger.warning(
                "%r carries no %r, so it leaves a gap in %r.",
                self.source,
                field,
                self.name,
            )
        else:
            logger.warning(
                "%r is not a number, so %r leaves a gap in %r.",
                value,
                field,
                self.name,
            )

    def value(self, event: Event, field: str) -> float | None:
        """Read a field of an event as a number."""
        if field not in event.payload:
            self.warn(field, None)
            return None

        raw = event.payload[field]
        value = numeric(raw)

        if value is None and raw is not None:
            self.warn(field, raw)

        return value

    def render(self, events: Sequence[Event]) -> dict[str, Any]:
        """Build the whole card from the events kept for its source."""
        raise NotImplementedError

    async def page(
        self,
        events: Sequence[Event],
        cursor: str | None,
        context: Context,
        host_loop: asyncio.AbstractEventLoop | None = None,
    ) -> dict[str, Any]:
        """One page of this widget's rows, starting after `cursor`.

        `cursor` is `None` for the first page. `context` and `host_loop`
        only matter to a widget that calls out to a host-supplied callable
        to build it. Only called on a `paginated` widget.
        """
        raise NotImplementedError

    def update(self, event: Event) -> dict[str, Any] | None:
        """Build the change a single new event makes, if it makes one."""
        raise NotImplementedError

    def accumulate(self, event: Event) -> None:
        """Update this widget's own state from a new event, if it persists anything."""

    def snapshot(self) -> dict[str, Any] | None:
        """This widget's current state to persist, or `None` if it isn't persisting."""
        return None

    def restore(self, data: dict[str, Any]) -> None:
        """Seed this widget's state from a previously persisted snapshot."""


def build(name: str, *, type: str = "line", **options: Any) -> Widget:
    """Build a widget of a registered type.

    Without an explicit source, the widget's own name doubles as its source.

    ## Example

    ```python
    build("latency", type="timeseries", size=2)
    ```
    """
    if type not in WIDGETS:
        known = ", ".join(sorted(WIDGETS))
        raise ValueError(f"There is no {type!r} widget type. Known types: {known}.")

    options.setdefault("source", name)

    return WIDGETS[type](name=name, **options)
