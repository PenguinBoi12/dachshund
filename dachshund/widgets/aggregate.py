from dataclasses import KW_ONLY, dataclass, field
from datetime import timedelta
from typing import Any, Mapping, Sequence

from dachshund.storage.events import Bucket, Event
from dachshund.widgets.persistable import PersistableWidget
from dachshund.widgets.window import PERIODS, Period, Window

AGGREGATES = ("last", "count", "sum", "average", "min", "max", "distinct")
WINDOWED = AGGREGATES[1:]


def aggregated(bucket: Bucket, aggregate: str) -> float | None:
    """`aggregate` of what `bucket` holds, `None` when it holds no number to tell.

    ## Example

    ```python
    aggregated(bucket, "average")
    ```
    """
    if aggregate == "count":
        return bucket.count

    if aggregate == "distinct":
        return None if bucket.distinct is None else len(bucket.distinct)

    if not bucket.values:
        return None

    if aggregate == "sum":
        return bucket.sum

    if aggregate == "average":
        return bucket.sum / bucket.values

    if aggregate == "min":
        return bucket.min

    if aggregate == "max":
        return bucket.max

    raise ValueError(f"Unknown aggregate {aggregate!r}.")


def merged(buckets: Sequence[Bucket]) -> Bucket:
    """One bucket holding what all of `buckets` do."""
    distinct: set[str] | None = set()
    total = Bucket(buckets[0].start if buckets else 0.0, distinct=distinct)

    for bucket in buckets:
        total.add(bucket.count, bucket.values, bucket.sum, bucket.min, bucket.max)

        if bucket.distinct is None or total.distinct is None:
            total.distinct = None
        else:
            total.distinct |= bucket.distinct

    return total


def check(name: str, aggregate: str | None, allowed: Sequence[str | None]) -> None:
    """Raise unless `aggregate` is one of `allowed`."""
    if aggregate not in allowed:
        choices = ", ".join(repr(each) for each in allowed)
        raise ValueError(
            f"{name!r} can't aggregate {aggregate!r}, use one of {choices}."
        )


def check_over(name: str, over: Any) -> None:
    """Raise unless `over` is a window: a timedelta or a period."""
    if not isinstance(over, timedelta) and over not in PERIODS:
        raise ValueError(
            f"{name!r} has over={over!r}, use a timedelta or one of {', '.join(PERIODS)}."
        )


@dataclass
class AggregatedWidget(PersistableWidget):
    """A widget showing one number of its source: the latest, or an aggregate over a window.

    Subclass it and write `render_value()`, which turns the number into the
    payload the renderer draws. See [Aggregating](../guides/custom-widgets.md#aggregating).

    ## Example

    ```python
    @dataclass
    class Gauge(AggregatedWidget):
        type: ClassVar[str] = "gauge"
        script: ClassVar[Path] = Path(__file__).parent / "gauge.js"

        def render_value(self, value):
            return {"value": value}


    Gauge("latency", aggregate="average", over=timedelta(hours=1))
    ```

    ## Options

    - `y` (`str`) - The field read. Defaults to `"value"`.
    - `aggregate` (`str`) - `"last"` for the latest number, or `"count"`,
      `"sum"`, `"average"`, `"min"`, `"max"` or `"distinct"` over `over`.
      Defaults to `"last"`.
    - `over` (`timedelta | str`) - The window: a `timedelta` back from now, or
      the current `"day"`, `"week"` or `"month"` in the dashboard's `timezone`.
      Defaults to `None`, everything stored. Not for `"last"`.
    - `persist` (`bool`) - Keeps the latest number across restarts, for
      `"last"` only: windows are rebuilt from stored events. Needs the
      dashboard's `storage`. Defaults to `False`.
    """

    _: KW_ONLY

    y: str = "value"
    aggregate: str = "last"
    over: timedelta | Period | None = None

    kept: dict[str, Any] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        super().__post_init__()
        check(self.name, self.aggregate, AGGREGATES)

        if self.aggregate == "last":
            if self.over is not None:
                raise ValueError(
                    f"{self.name!r} has an `over` but shows the last value, "
                    "give it an aggregate."
                )
            return

        if self.over is not None:
            check_over(self.name, self.over)

        if self.persist:
            raise ValueError(
                f"{self.name!r} aggregates over stored events, which are kept "
                "already: persist=True is only for aggregate='last'."
            )

    def window(self) -> Window | None:
        """`aggregate` of `y` over `over`, `None` for `"last"`."""
        if self.aggregate == "last":
            return None

        return Window(fields=(self.y,), aggregate=self.aggregate, over=self.over)

    def render_value(self, value: float | None) -> dict[str, Any]:
        """The payload drawn for `value`, `None` before there's one to show."""
        raise NotImplementedError(f"{type(self).__name__} must write render_value().")

    def render(self, events: Sequence[Event]) -> dict[str, Any]:
        """The latest number of `y`, or `None` before anything arrives.

        A persisting widget reads its own kept reading instead, since that
        covers more than whatever events are still around to re-read.
        """
        if self.persist:
            value = self.kept["value"] if self.kept else None
        else:
            value = self.value(events[-1], self.y) if events else None

        return self.render_value(value)

    def render_buckets(self, buckets: Mapping[str, Sequence[Bucket]]) -> dict[str, Any]:
        """The aggregate over the window's buckets."""
        return self.render_value(aggregated(merged(buckets[self.y]), self.aggregate))

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
