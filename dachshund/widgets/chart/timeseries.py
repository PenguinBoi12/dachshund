from dataclasses import KW_ONLY, dataclass
from datetime import timedelta
from typing import Any, ClassVar, Mapping, Sequence

from dachshund.storage.events import Bucket, Event
from dachshund.widgets.aggregate import WINDOWED, aggregated, check, check_over
from dachshund.widgets.chart.line import LineChart
from dachshund.widgets.window import Period


@dataclass
class TimeSeriesChart(LineChart):
    """A line over time: one point per event, or an aggregate per bucket of time.

    ## Example

    ```python
    with dachshund.row():
        dachshund.add(TimeSeriesChart("latency", y=["p50", "p95"]))
        dachshund.add(
            TimeSeriesChart("requests", aggregate="count", every=timedelta(minutes=1))
        )
    dachshund.emit("latency", p50=10, p95=40)
    ```

    ## Options

    - `y` (`str | list[str]`) - The field drawn, or one line per field.
      Defaults to `"value"`.
    - `aggregate` (`str`) - `"count"`, `"sum"`, `"average"`, `"min"`, `"max"`
      or `"distinct"` of each field per bucket. Defaults to `None`, a point
      per event. See [Aggregating](../guides/widgets.md#aggregating).
    - `every` (`timedelta`) - A bucket's length, a whole number of minutes.
      Whole days start at midnight in the dashboard's `timezone`. Required
      with `aggregate`.
    - `over` (`timedelta | str`) - How far back the chart goes: a `timedelta`,
      or the current `"day"`, `"week"` or `"month"`. Defaults to `None`, the
      latest 500 buckets.

    A point's x is the time its event was emitted, or its bucket's start, so
    there's no `x` option.
    """

    _: KW_ONLY

    x: str = ""
    aggregate: str | None = None
    every: timedelta | None = None
    over: timedelta | Period | None = None

    type: ClassVar[str] = "timeseries"

    def __post_init__(self) -> None:
        super().__post_init__()

        if self.x:
            raise ValueError("A timeseries takes its x from when events happen.")

        check(self.name, self.aggregate, (None, *WINDOWED))

        if self.aggregate is None:
            if self.every is not None or self.over is not None:
                raise ValueError(
                    f"{self.name!r} has `every` or `over` but no aggregate, "
                    "give it one."
                )
            return

        if self.every is None:
            raise ValueError(f"{self.name!r} aggregates, give it `every`.")

        if self.every.total_seconds() < 60 or self.every.total_seconds() % 60:
            raise ValueError(
                f"{self.name!r} has every={self.every!r}, use a whole number of minutes."
            )

        if self.over is not None:
            check_over(self.name, self.over)

    @property
    def windowed(self) -> bool:
        """Whether this chart is built from stored buckets, not its kept events."""
        return self.aggregate is not None

    @property
    def fields(self) -> tuple[str, ...]:
        """The fields summarized, one line each."""
        return self.series

    def at(self, event: Event) -> float:
        """When the event happened, as the seconds uPlot expects."""
        return event.at.timestamp()

    def render_buckets(self, buckets: Mapping[str, Sequence[Bucket]]) -> dict[str, Any]:
        """One point per bucket, the aggregate of each field."""
        assert self.aggregate is not None
        starts = [bucket.start for bucket in buckets[self.series[0]]]

        return {
            "series": list(self.series),
            "x": starts,
            "y": [
                [aggregated(bucket, self.aggregate) for bucket in buckets[field]]
                for field in self.series
            ],
        }
