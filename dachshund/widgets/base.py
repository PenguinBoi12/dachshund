import asyncio
import logging
from dataclasses import KW_ONLY, dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Sequence

from dachshund.actions import Context
from dachshund.storage.events import Event
from dachshund.widgets.value import numeric

logger = logging.getLogger("dachshund")

WIDGETS: dict[str, "type[Widget]"] = {}


@dataclass
class Widget:
    """A card on the dashboard, built from the events of its source.

    Every built-in widget subclasses it. A subclass with a `type` of its own is
    registered when the class is defined. See the
    [Custom Widgets](../guides/custom-widgets.md) guide.

    ## Example

    ```python
    class Gauge(Widget):
        type: ClassVar[str] = "gauge"
        script: ClassVar[Path] = Path(__file__).parent / "gauge.js"

        def render(self, events):
            return {"value": self.value(events[-1], "value") if events else None}
    ```

    ## Options

    - `name` (`str`) - The widget's unique name. Required.
    - `source` (`str`) - The events it's built from. Defaults to `name`.
    - `title` (`str`) - The card's title. Defaults to `name`, underscores as
      spaces.
    - `actions` (`list[str]`) - The actions shown as buttons on the card, see
      [Actions](../reference/actions.md). Defaults to `[]`.
    - `action_args` (`dict[str, dict]`) - The arguments each action is called
      with, by action name. Defaults to `{}`.

    ## Class attributes

    - `type` (`str`) - The renderer drawing the card in the browser.
    - `op` (`str`) - How the browser applies an `update()`: `"replace"`
      redraws the card, `"append"` adds a point. Defaults to `"replace"`.
    - `script` (`Path`) - The renderer's JavaScript file, served and loaded
      with the page. Defaults to `None`.
    - `style` (`Path`) - A stylesheet for the renderer. Defaults to `None`.
    - `renders_own_actions` (`bool`) - The renderer places action buttons
      itself, like `Table` does per row. Defaults to `False`.
    - `paginated` (`bool`) - Rows are fetched a page at a time through
      `page()`. Defaults to `False`.
    - `rollup_safe` (`bool`) - Old events of the source may be averaged
      together, see `EventStore.compact`. Defaults to `False`.
    """

    name: str

    _: KW_ONLY

    source: str = ""
    title: str | None = None
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
        # than a `type` of its own and being imported once. An intermediate
        # base without its own `type` is never built by name.
        if "type" in cls.__dict__:
            WIDGETS[cls.type] = cls

    def __post_init__(self) -> None:
        if not self.source:
            self.source = self.name

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
