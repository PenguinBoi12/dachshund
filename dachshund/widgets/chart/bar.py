from dataclasses import KW_ONLY, dataclass
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
    """

    _: KW_ONLY

    x: str
    y: str = "value"

    type: ClassVar[str] = "bar"
    op: ClassVar[str] = "replace"

    @property
    def series(self) -> tuple[str, ...]:
        """The fields this chart draws, a set of bars each."""
        return (self.y,)

    def render(self, events: Sequence[Event]) -> dict[str, Any]:
        """Total every event into the bar of its category."""
        totals: dict[str, float] = {}

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
