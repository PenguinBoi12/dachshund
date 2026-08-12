from dataclasses import dataclass
from typing import Any, ClassVar, Sequence

from dachshund.storage.events import Event
from dachshund.widgets.base import Widget


@dataclass
class LineGraph(Widget):
    """A line of one value over time.

    Fed by a source, it is inherently live: every event appends a point.

    ## Example

    ```python
    dachshund.graph("latency", size=2)
    dachshund.emit("latency", value=96)
    ```
    """

    field: str = "value"

    type: ClassVar[str] = "line"
    op: ClassVar[str] = "append"

    def render(self, events: Sequence[Event]) -> dict[str, Any]:
        """Build the two columns uPlot draws a series from."""
        return {
            "x": [self.at(event) for event in events],
            "y": [self.value(event) for event in events],
        }

    def update(self, event: Event) -> dict[str, Any]:
        """Build the point a new event appends."""
        return {"x": self.at(event), "y": self.value(event)}

    def at(self, event: Event) -> float:
        """When the event happened, as the seconds uPlot expects."""
        return event.at.timestamp()

    def value(self, event: Event) -> float:
        """What the event plots, defaulting to 1 so bare events can be counted."""
        return float(event.payload.get(self.field, 1))
