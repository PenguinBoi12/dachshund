from dataclasses import KW_ONLY, dataclass
from typing import ClassVar

from dachshund.storage.events import Event
from dachshund.widgets.chart.line import LineChart


@dataclass
class TimeSeriesChart(LineChart):
    """A line drawn over time, a point per event.

    `y` names the field drawn, or several fields for several lines. There is
    no `x` to give: a point sits where its event happened.

    ## Example

    ```python
    dachshund.chart("requests", type="timeseries")
    dachshund.emit("requests", value=1)
    ```

    Plotting a reading rather than counting events:

    ```python
    dachshund.chart("latency", type="timeseries", title="Response time", size=2)
    dachshund.emit("latency", value=96)
    ```

    A line per field:

    ```python
    dachshund.chart("send_latency", type="timeseries", y=["p50", "p95", "p99"])
    dachshund.emit("send_latency", p50=10, p95=40, p99=99)
    ```
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
