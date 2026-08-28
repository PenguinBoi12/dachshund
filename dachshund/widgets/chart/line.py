from dataclasses import KW_ONLY, dataclass
from pathlib import Path
from typing import Any, ClassVar, Sequence

from dachshund.storage.events import Event
from dachshund.widgets.base import Widget
from dachshund.widgets.value import numeric


@dataclass
class LineChart(Widget):
    """A line of one value against another, both read from the event.

    `x` names the field placing a point and `y` the field drawn, or several
    fields for several lines sharing that x. An event missing `x` has
    nowhere to sit, so it draws nothing.

    Use [TimeSeriesChart][dachshund.TimeSeriesChart] instead to draw against
    the time events happened.

    ## Example

    ```python
    dachshund.chart("throughput", type="line", x="requests", y="latency")
    dachshund.emit("throughput", requests=120, latency=96)
    ```

    A line per field, against one x:

    ```python
    dachshund.chart("perf", type="line", x="load", y=["p50", "p95"])
    dachshund.emit("perf", load=10, p50=4, p95=20)
    ```
    """

    _: KW_ONLY

    x: str
    y: str | Sequence[str] = "value"

    type: ClassVar[str] = "line"
    op: ClassVar[str] = "append"
    script: ClassVar[Path] = Path(__file__).parent / "charts.js"
    style: ClassVar[Path] = Path(__file__).parent / "charts.css"
    rollup_safe: ClassVar[bool] = True

    def __post_init__(self) -> None:
        super().__post_init__()

        if not self.series:
            raise ValueError("A chart plots at least one y field.")

    @property
    def series(self) -> tuple[str, ...]:
        """The fields this chart draws, a line each."""
        if isinstance(self.y, str):
            return (self.y,)

        return tuple(self.y)

    def render(self, events: Sequence[Event]) -> dict[str, Any]:
        """Build the columns uPlot draws its series from."""
        rows = [row for row in map(self.update, events) if row is not None]

        return {
            "series": list(self.series),
            "x": [row["x"] for row in rows],
            "y": [
                [row["y"][index] for row in rows] for index in range(len(self.series))
            ],
        }

    def update(self, event: Event) -> dict[str, Any] | None:
        """Build the row a new event appends, a value per series.

        Returns `None` when the event has no readable x to place it at.
        """
        at = self.at(event)

        if at is None:
            self.warn(self.x, event.payload.get(self.x))
            return None

        return {
            "x": at,
            "y": [self.value(event, field) for field in self.series],
        }

    def at(self, event: Event) -> float | None:
        """Where along the x axis the event's own reading puts it.

        Returns `None` when the event carries no usable reading.
        """
        return numeric(event.payload.get(self.x))
