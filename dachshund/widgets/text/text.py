from dataclasses import KW_ONLY, dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Sequence

from dachshund.storage.events import Event
from dachshund.widgets.persistable import PersistableWidget
from dachshund.widgets.markup import render_markdown


@dataclass
class Text(PersistableWidget):
    """The latest markdown of its source, rendered to sanitized HTML.

    Raw HTML in the markdown is escaped, and only `http`, `https` and `mailto`
    links are kept.

    ## Example

    ```python
    with dachshund.row():
        dachshund.add(Text("changelog", title="Release Notes"))
    dachshund.emit("changelog", value="**v1.2** fixed the thing.")
    ```

    ## Options

    - `y` (`str`) - The field read. Defaults to `"value"`.
    - `persist` (`bool`) - Keeps the latest text across restarts. Needs the
      dashboard's `storage`. Defaults to `False`.
    """

    _: KW_ONLY

    y: str = "value"

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
        """Keep the latest markdown of `y`."""
        text = self._read(event)

        if text is None:
            return

        self.kept = {"value": text}

    def snapshot(self) -> dict[str, Any]:
        """The kept text."""
        return self.kept or {}

    def restore(self, data: dict[str, Any]) -> None:
        """Pick up where the last persisted snapshot left off."""
        self.kept = data

    def _read(self, event: Event) -> str | None:
        if self.y not in event.payload:
            self.warn(self.y, None)
            return None

        raw = event.payload[self.y]
        return None if raw is None else str(raw)
