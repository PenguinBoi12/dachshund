import json
from dataclasses import KW_ONLY, dataclass
from pathlib import Path
from typing import Any, ClassVar, Sequence

from dachshund.storage.events import DISTINCT_CAP, Bucket, Event
from dachshund.widgets.aggregate import WINDOWED, aggregated, check
from dachshund.widgets.state import KeyedWidget

UNLABELLED = "—"


@dataclass
class BarChart(KeyedWidget):
    """A bar per category, aggregating a field of its events: its total by default.

    Bars keep the order their categories first appeared in.

    ## Example

    ```python
    with dachshund.row():
        dachshund.add(BarChart("commands", x="name"))
    dachshund.emit("commands", name="/ban", value=1)
    ```

    ## Options

    - `x` (`str`) - The field naming an event's category. Required.
    - `y` (`str`) - The field aggregated per category. Defaults to `"value"`.
    - `aggregate` (`str`) - `"sum"`, `"count"`, `"average"`, `"min"`, `"max"`
      or `"distinct"` of `y` per category. `"count"` counts events, whatever
      `y`. Defaults to `"sum"`. See [Aggregating](../guides/widgets.md#aggregating).
    - `persist` (`bool`) - Keeps the bars across restarts. Needs the
      dashboard's `storage`. Defaults to `False`.

    ## Removing a category

    A truthy `_delete` field removes the event's category:

    ```python
    dachshund.emit("commands", name="/ban", _delete=True)
    ```

    On a persisted chart, `sweep(before)` removes every category not seen
    since `before`, see [KeyedWidget][dachshund.widgets.state.KeyedWidget].
    """

    _: KW_ONLY

    x: str
    y: str = "value"
    aggregate: str = "sum"

    type: ClassVar[str] = "bar"
    op: ClassVar[str] = "replace"
    script: ClassVar[Path] = Path(__file__).parent / "charts.js"
    style: ClassVar[Path] = Path(__file__).parent / "charts.css"

    def __post_init__(self) -> None:
        super().__post_init__()
        check(self.name, self.aggregate, WINDOWED)

    @property
    def series(self) -> tuple[str, ...]:
        """The fields this chart draws, a set of bars each."""
        return (self.y,)

    def render(self, events: Sequence[Event]) -> dict[str, Any]:
        """Aggregate every event into the bar of its category.

        A persisting chart reads its own kept bars instead, since those cover
        more than whatever events are still around to re-aggregate.
        """
        if self.persist:
            entries = self.state.entries
        else:
            entries = {}

            for event in events:
                category = self.category(event)
                entries[category] = self.tally(entries.get(category), event)

        bars = {}

        for category, entry in entries.items():
            value = aggregated(_bucket(entry), self.aggregate)

            if value is not None:
                bars[category] = value

        return {
            "series": list(self.series),
            "x": list(bars),
            "y": [list(bars.values())],
        }

    def category(self, event: Event) -> str:
        """Which bar the event belongs to."""
        return str(event.payload.get(self.x, UNLABELLED))

    def tally(self, entry: Any, event: Event) -> dict[str, Any]:
        """A category's entry with `event` added: how many events, and `y`'s numbers."""
        kept = _entry(entry)
        value = self.value(event, self.y) if self.aggregate != "count" else None

        kept["count"] += 1

        if value is not None:
            kept["values"] += 1
            kept["sum"] += value
            kept["min"] = value if kept["min"] is None else min(kept["min"], value)
            kept["max"] = value if kept["max"] is None else max(kept["max"], value)

        if self.aggregate == "distinct" and kept["distinct"] is not None:
            raw = event.payload.get(self.y)

            if raw is not None:
                labels = set(kept["distinct"]) | {_label(raw)}
                kept["distinct"] = (
                    sorted(labels) if len(labels) <= DISTINCT_CAP else None
                )

        return kept

    def accumulate(self, event: Event) -> None:
        """Fold one more event into the kept bars.

        A truthy `_delete` removes the category instead of adding to it.
        """
        category = self.category(event)

        if event.payload.get("_delete"):
            self.state.remove(category)
            return

        entry = self.tally(self.state.entries.get(category), event)
        self.state.upsert(category, entry, event.at.timestamp())


def _entry(entry: Any) -> dict[str, Any]:
    """A copy of a category's entry, a total kept before aggregates read as one event."""
    if entry is None:
        return {
            "count": 0,
            "values": 0,
            "sum": 0.0,
            "min": None,
            "max": None,
            "distinct": [],
        }

    if isinstance(entry, (int, float)):
        return {
            "count": 1,
            "values": 1,
            "sum": float(entry),
            "min": float(entry),
            "max": float(entry),
            "distinct": None,
        }

    return dict(entry)


def _bucket(entry: Any) -> Bucket:
    kept = _entry(entry)
    distinct = kept["distinct"]

    return Bucket(
        0.0,
        count=kept["count"],
        values=kept["values"],
        sum=kept["sum"],
        min=kept["min"],
        max=kept["max"],
        distinct=None if distinct is None else set(distinct),
    )


def _label(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value)
