from abc import ABC, abstractmethod
from dataclasses import KW_ONLY, dataclass
from typing import Any, TypeGuard

from dachshund.storage.events import Event
from dachshund.widgets.base import Widget


@dataclass
class PersistableWidget(Widget, ABC):
    """A `Widget` that can keep its state across a restart, if asked to.

    Off by default: built without `persist=True`, it behaves like any other
    `Widget` and none of the hooks below are called. With `persist=True`, its
    state is saved to the dashboard's `Storage` and `render()` reads that
    state instead of the kept events.

    For state that's one entry per string key, subclass
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


def persisting(widget: Widget) -> TypeGuard[PersistableWidget]:
    """Whether `widget` was built with `persist=True`."""
    return isinstance(widget, PersistableWidget) and widget.persist
