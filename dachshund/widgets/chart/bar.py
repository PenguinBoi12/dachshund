from dataclasses import KW_ONLY, dataclass
from pathlib import Path
from typing import Any, ClassVar, Sequence

from dachshund.storage.events import Event
from dachshund.widgets.state import KeyedWidget

UNLABELLED = "—"


@dataclass
class BarChart(KeyedWidget):
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
    dashboard first, there's no default. A truthy `_delete` field removes a
    category instead of adding to it:

    ```python
    from dachshund.storage.sqlite import SQLiteStorage

    dashboard = Dashboard(storage=SQLiteStorage("widget_state.db"))
    commands = dashboard.chart("commands", type="bar", x="name", persist=True)
    dashboard.emit("commands", name="/ban", value=1)
    dashboard.emit("commands", name="/ban", _delete=True)

    # after a full resync (e.g. re-emitting every current category):
    commands.sweep(before=time.time())
    ```
    """

    _: KW_ONLY

    x: str
    y: str = "value"

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
            totals = self.state.entries
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
        """Fold one more event into the kept totals, if persisting.

        A truthy `_delete` removes the category instead of adding to it.
        """
        if not self.persist:
            return

        category = self.category(event)

        if event.payload.get("_delete"):
            self.state.remove(category)
            return

        value = self.value(event, self.y)

        if value is None:
            return

        current = self.state.entries.get(category, 0.0)
        self.state.upsert(category, current + value, event.at.timestamp())
