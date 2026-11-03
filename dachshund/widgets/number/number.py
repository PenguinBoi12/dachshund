from dataclasses import KW_ONLY, dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Sequence

from dachshund.storage.events import Event
from dachshund.widgets.persistable import PersistableWidget


@dataclass
class Number(PersistableWidget):
    """The latest number of its source, shown big.

    ## Example

    ```python
    dachshund.row(Number("cpu", title="CPU Load", unit="%"))
    dachshund.emit("cpu", value=42)
    ```

    ## Options

    - `y` (`str`) - The field read. Defaults to `"value"`.
    - `unit` (`str`) - Shown next to the number, as is. Defaults to `None`.
    - `persist` (`bool`) - Keeps the latest number across restarts. Needs the
      dashboard's `storage`. Defaults to `False`.
    """

    _: KW_ONLY

    y: str = "value"
    unit: str | None = None

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
        """Keep the latest reading of `y`."""
        value = self.value(event, self.y)

        if value is None:
            return

        self.kept = {"value": value}

    def snapshot(self) -> dict[str, Any]:
        """The kept reading."""
        return self.kept or {}

    def restore(self, data: dict[str, Any]) -> None:
        """Pick up where the last persisted snapshot left off."""
        self.kept = data
