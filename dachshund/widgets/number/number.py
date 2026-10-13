from dataclasses import KW_ONLY, dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Sequence

from dachshund.storage.events import Event
from dachshund.widgets.base import Widget


@dataclass
class Number(Widget):
    """The latest number from its source, big.

    `y` names the field read and defaults to `value`. `unit` is shown next to
    the number, unscaled, e.g. `"ms"` or `"%"`.

    ## Example

    ```python
    dachshund.chart("cpu", type="number", title="CPU Load", unit="%")
    dachshund.emit("cpu", value=42)
    ```

    With `persist=True`, the reading survives a restart instead of only
    covering whatever's still kept in the event log. This needs
    `storage=...` configured on the dashboard first, there's no default.

    ```python
    from dachshund.storage.sqlite import SQLiteStorage

    dachshund.init(storage=SQLiteStorage("widget_state.db"))
    dachshund.widget("cpu", type="number", unit="%", persist=True)
    dachshund.emit("cpu", value=42)
    ```
    """

    _: KW_ONLY

    y: str = "value"
    unit: str | None = None
    persist: bool = False

    kept: dict[str, Any] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    type: ClassVar[str] = "number"
    op: ClassVar[str] = "replace"
    script: ClassVar[Path] = Path(__file__).parent / "number.js"
    style: ClassVar[Path] = Path(__file__).parent / "number.css"

    def render(self, events: Sequence[Event]) -> dict[str, Any]:
        """The most recent reading of `y`, or `None` before anything arrives.

        A persisting widget reads its own kept reading instead, since that
        covers more than whatever events are still around to re-read.
        """
        if self.persist:
            value = self.kept["value"] if self.kept else None
        else:
            value = self.value(events[-1], self.y) if events else None

        return {"value": value, "unit": self.unit}

    def accumulate(self, event: Event) -> None:
        """Keep the latest reading of `y`, if persisting."""
        if not self.persist:
            return

        value = self.value(event, self.y)

        if value is None:
            return

        self.kept = {"value": value}

    def snapshot(self) -> dict[str, Any] | None:
        """The kept reading, or `None` when this widget isn't persisting."""
        return self.kept if self.persist else None

    def restore(self, data: dict[str, Any]) -> None:
        """Pick up where the last persisted snapshot left off."""
        self.kept = data
