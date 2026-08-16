from dataclasses import KW_ONLY, dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Sequence

from dachshund.storage.events import Event
from dachshund.widgets.base import Widget

UNLABELLED = "—"


@dataclass
class BarChart(Widget):
    """A bar per category, totalling the events of its source.

    `x` names the field the categories come from and `y` what is totalled.

    A bar is a snapshot, not a stream: an event replaces its bar's height
    rather than adding a point, and the whole chart is redrawn on every
    update. Bars keep the order their categories first appeared in.

    ## Example

    ```python
    dachshund.chart("commands", type="bar", x="name")
    dachshund.emit("commands", name="/ban", value=1)
    ```

    Totalling a field rather than counting, fed by another name:

    ```python
    dachshund.chart("load", type="bar", x="name", y="ms", source="on_command")
    dachshund.emit("on_command", name="/ban", ms=96)
    ```

    With `persist=True`, totals survive a restart instead of only covering
    the events currently kept. This needs `storage=...` configured on the
    dashboard first, there's no default:

    ```python
    from dachshund.storage.sqlite import SQLiteStorage

    dashboard = Dashboard(storage=SQLiteStorage("widget_state.db"))
    dashboard.chart("commands", type="bar", x="name", persist=True)
    dashboard.emit("commands", name="/ban", value=1)
    ```
    """

    _: KW_ONLY

    x: str
    y: str = "value"
    persist: bool = False

    totals: dict[str, float] = field(
        default_factory=dict,
        init=False,
        repr=False,
        compare=False,
    )

    type: ClassVar[str] = "bar"
    op: ClassVar[str] = "replace"
    script: ClassVar[Path] = Path(__file__).parent / "charts.js"
    style: ClassVar[Path] = Path(__file__).parent / "charts.css"

    @property
    def series(self) -> tuple[str, ...]:
        """The fields this chart draws, a set of bars each."""
        return (self.y,)

    def render(self, events: Sequence[Event]) -> dict[str, Any]:
        """Total every event into the bar of its category.

        A persisting chart reads its own kept totals instead, since those
        cover more than whatever events are still around to re-total.
        """
        if self.persist:
            totals = self.totals
        else:
            totals = {}

            for event in events:
                value = self.value(event, self.y)

                # A gap has no meaning in a total, so it is left out of one.
                if value is None:
                    continue

                category = self.category(event)
                totals[category] = totals.get(category, 0.0) + value

        return {
            "series": list(self.series),
            "x": list(totals),
            "y": [list(totals.values())],
        }

    def category(self, event: Event) -> str:
        """Which bar the event belongs to."""
        return str(event.payload.get(self.x, UNLABELLED))

    def accumulate(self, event: Event) -> None:
        """Fold one more event into the kept totals, if persisting."""
        if not self.persist:
            return

        value = self.value(event, self.y)

        if value is None:
            return

        category = self.category(event)
        self.totals[category] = self.totals.get(category, 0.0) + value

    def snapshot(self) -> dict[str, Any] | None:
        """The kept totals, or `None` when this chart isn't persisting."""
        return {"totals": self.totals} if self.persist else None

    def restore(self, data: dict[str, Any]) -> None:
        """Pick up where the last persisted snapshot left off."""
        self.totals = dict(data.get("totals", {}))
