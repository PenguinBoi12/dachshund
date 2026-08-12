from dataclasses import dataclass
from typing import Any, ClassVar, Sequence

from dachshund.storage.events import Event

MAX_SIZE = 3


@dataclass
class Widget:
    """A card on the dashboard, fed by an event source.

    A widget turns events into whatever its renderer draws. `render` builds the
    whole card, from every event kept for its source. `update` builds a single
    incremental change, and `op` tells the client how to apply it.

    Subclasses pair with a renderer registered under the same `type` in the
    client's dispatch table.
    """

    name: str
    source: str
    title: str | None = None
    size: int = 1

    type: ClassVar[str] = "widget"
    op: ClassVar[str] = "replace"

    def __post_init__(self) -> None:
        if not 1 <= self.size <= MAX_SIZE:
            raise ValueError(f"A widget spans 1 to {MAX_SIZE} columns.")

    @property
    def label(self) -> str:
        """The heading shown on the card."""
        return self.title or self.name.replace("_", " ")

    def render(self, events: Sequence[Event]) -> dict[str, Any]:
        """Build the whole card from the events kept for its source."""
        raise NotImplementedError

    def update(self, event: Event) -> dict[str, Any]:
        """Build the change a single new event makes to the card."""
        raise NotImplementedError
