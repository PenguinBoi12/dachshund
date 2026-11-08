from abc import ABC, abstractmethod
from dataclasses import KW_ONLY, dataclass
from typing import Any, TypeGuard

from dachshund.storage.events import Event
from dachshund.widgets.base import Widget


@dataclass
class PersistableWidget(Widget, ABC):
    """A `Widget` whose state can be kept across restarts.

    With `persist=True`, every event goes through `accumulate()`, the state from
    `snapshot()` is saved to the dashboard's `storage`, and `restore()` seeds it
    on start. Without it, none of the three is called.

    For state with one entry per key, subclass
    [KeyedWidget][dachshund.widgets.state.KeyedWidget] instead.

    ## Example

    ```python
    @dataclass
    class Gauge(PersistableWidget):
        last: float | None = field(default=None, init=False)

        type: ClassVar[str] = "gauge"

        def accumulate(self, event):
            self.last = self.value(event, "value")

        def snapshot(self):
            return {"last": self.last}

        def restore(self, data):
            self.last = data.get("last")
    ```

    ## Options

    - `persist` (`bool`) - Keeps the widget's state across restarts. Needs
      the dashboard's `storage`. Defaults to `False`.
    """

    _: KW_ONLY

    persist: bool = False

    @abstractmethod
    def accumulate(self, event: Event) -> None:
        """Fold a new event into this widget's state."""

    @abstractmethod
    def snapshot(self) -> dict[str, Any]:
        """This widget's current state, to save."""

    @abstractmethod
    def restore(self, data: dict[str, Any]) -> None:
        """Seed this widget's state from a saved snapshot."""


def is_persisting(widget: Widget) -> TypeGuard[PersistableWidget]:
    """Whether `widget` was built with `persist=True`."""
    return isinstance(widget, PersistableWidget) and widget.persist
