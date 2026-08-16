from dataclasses import KW_ONLY, dataclass
from pathlib import Path
from typing import Any, ClassVar, Sequence

from dachshund.storage.events import Event
from dachshund.widgets.base import Widget


@dataclass
class Number(Widget):
    """The latest number from its source, big.

    `y` names the field read and defaults to `value`.

    ## Example

    ```python
    dachshund.chart("cpu", type="number", title="CPU Load")
    dachshund.emit("cpu", value=42)
    ```
    """

    _: KW_ONLY

    y: str = "value"

    type: ClassVar[str] = "number"
    op: ClassVar[str] = "replace"
    script: ClassVar[Path] = Path(__file__).parent / "number.js"
    style: ClassVar[Path] = Path(__file__).parent / "number.css"

    def render(self, events: Sequence[Event]) -> dict[str, Any]:
        """The most recent reading of `y`, or `None` before anything arrives."""
        return {"value": self.value(events[-1], self.y) if events else None}
