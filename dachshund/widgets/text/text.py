from dataclasses import KW_ONLY, dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Sequence

from dachshund.storage.events import Event
from dachshund.widgets.base import Widget
from dachshund.widgets.markup import render_markdown


@dataclass
class Text(Widget):
    """The latest markdown from its source, rendered to sanitized HTML.

    `y` names the field read and defaults to `value`.

    ## Example

    ```python
    dachshund.widget("changelog", type="text", title="Release Notes")
    dachshund.emit("changelog", value="**v1.2** fixed the thing.")
    ```

    With `persist=True`, the text survives a restart instead of only
    covering whatever's still kept in the event log. This needs
    `storage=...` configured on the dashboard first, there's no default.

    ```python
    from dachshund.storage.sqlite import SQLiteStorage

    daschund.init(storage=SQLiteStorage("widget_state.db"))
    daschund.widget("changelog", type="text", persist=True)
    daschund.emit("changelog", value="**v1.2** fixed the thing.")
    ```
    """

    _: KW_ONLY

    y: str = "value"
    persist: bool = False

    kept: dict[str, Any] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    type: ClassVar[str] = "text"
    op: ClassVar[str] = "replace"
    script: ClassVar[Path] = Path(__file__).parent / "text.js"
    style: ClassVar[Path] = Path(__file__).parent / "text.css"

    def render(self, events: Sequence[Event]) -> dict[str, Any]:
        """The most recent markdown of `y`, rendered to HTML.

        A persisting widget reads its own kept text instead, since that
        covers more than whatever events are still around to re-read.
        """
        if self.persist:
            text = self.kept["value"] if self.kept else None
        else:
            text = self._read(events[-1]) if events else None

        return {"html": render_markdown(text) if text is not None else None}

    def accumulate(self, event: Event) -> None:
        """Keep the latest markdown of `y`, if persisting."""
        if not self.persist:
            return

        text = self._read(event)

        if text is None:
            return

        self.kept = {"value": text}

    def snapshot(self) -> dict[str, Any] | None:
        """The kept text, or `None` when this widget isn't persisting."""
        return self.kept if self.persist else None

    def restore(self, data: dict[str, Any]) -> None:
        """Pick up where the last persisted snapshot left off."""
        self.kept = data

    def _read(self, event: Event) -> str | None:
        if self.y not in event.payload:
            self.warn(self.y, None)
            return None

        raw = event.payload[self.y]
        return None if raw is None else str(raw)
