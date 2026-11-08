from dataclasses import KW_ONLY, dataclass
from pathlib import Path
from typing import Any, ClassVar

from dachshund.widgets.aggregate import AggregatedWidget


@dataclass
class Number(AggregatedWidget):
    """One number of its source, shown big: the latest, or an aggregate over a window.

    ## Example

    ```python
    with dachshund.row():
        dachshund.add(Number("cpu", title="CPU Load", unit="%"))
        dachshund.add(Number("requests", aggregate="count", over=timedelta(hours=1)))
    dachshund.emit("cpu", value=42)
    ```

    ## Options

    - `y` (`str`) - The field read. Defaults to `"value"`.
    - `aggregate` (`str`) - `"last"` for the latest number, or `"count"`,
      `"sum"`, `"average"`, `"min"`, `"max"` or `"distinct"` over `over`.
      Defaults to `"last"`. See [Aggregating](../guides/widgets.md#aggregating).
    - `over` (`timedelta | str`) - The window: a `timedelta` back from now, or
      the current `"day"`, `"week"` or `"month"` in the dashboard's `timezone`.
      Defaults to `None`, everything stored. Not for `"last"`.
    - `unit` (`str`) - Shown next to the number, as is. Defaults to `None`.
    - `persist` (`bool`) - Keeps the latest number across restarts, for
      `"last"` only. Needs the dashboard's `storage`. Defaults to `False`.
    """

    _: KW_ONLY

    unit: str | None = None

    type: ClassVar[str] = "number"
    op: ClassVar[str] = "replace"
    script: ClassVar[Path] = Path(__file__).parent / "number.js"
    style: ClassVar[Path] = Path(__file__).parent / "number.css"

    def render_value(self, value: float | None) -> dict[str, Any]:
        return {"value": value, "unit": self.unit}
