from dataclasses import KW_ONLY, dataclass
from typing import ClassVar

from dachshund.storage.events import Event
from dachshund.widgets.chart.line import LineChart


@dataclass
class TimeSeriesChart(LineChart):
    """A line over time, one point per event.

    ## Example

    ```python
    dachshund.add(TimeSeriesChart("latency", y=["p50", "p95"]))
    dachshund.emit("latency", p50=10, p95=40)
    ```

    ## Options

    - `y` (`str | list[str]`) - The field drawn, or one line per field.
      Defaults to `"value"`.

    A point's x is the time its event was emitted, so there's no `x` option.
    """

    _: KW_ONLY

    x: str = ""

    type: ClassVar[str] = "timeseries"

    def __post_init__(self) -> None:
        super().__post_init__()

        if self.x:
            raise ValueError("A timeseries takes its x from when events happen.")

    def at(self, event: Event) -> float:
        """When the event happened, as the seconds uPlot expects."""
        return event.at.timestamp()
