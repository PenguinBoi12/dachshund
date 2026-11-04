from dataclasses import KW_ONLY, dataclass
from pathlib import Path
from typing import Any, ClassVar, Sequence

from dachshund.storage.events import Event
from dachshund.widgets.state import KeyedWidget

UNLABELLED = "—"


@dataclass
class BarChart(KeyedWidget):
    """A bar per category, totalling a field of its events.

    Bars keep the order their categories first appeared in.

    ## Example

    ```python
    with dachshund.row():
        dachshund.add(BarChart("commands", x="name"))
    dachshund.emit("commands", name="/ban", value=1)
    ```

    ## Options

    - `x` (`str`) - The field naming an event's category. Required.
    - `y` (`str`) - The field added to the category's total. Defaults to
      `"value"`.
    - `persist` (`bool`) - Keeps the totals across restarts. Needs the
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
        """Fold one more event into the kept totals.

        A truthy `_delete` removes the category instead of adding to it.
        """
        category = self.category(event)

        if event.payload.get("_delete"):
            self.state.remove(category)
            return

        value = self.value(event, self.y)

        if value is None:
            return

        current = self.state.entries.get(category, 0.0)
        self.state.upsert(category, current + value, event.at.timestamp())
