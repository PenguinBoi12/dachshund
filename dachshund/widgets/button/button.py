from dataclasses import dataclass
from typing import Any, ClassVar, Sequence

from dachshund.storage.events import Event
from dachshund.widgets.base import Widget


@dataclass
class Button(Widget):
    """A card that's nothing but a title and its action buttons.

    No data of its own, `actions` (see [Widget][dachshund.Widget]) is the
    whole point of one. There's no row or event behind a click here, so an
    action needing arguments gets them from `action_args` instead, fixed at
    registration time.

    ## Example

    ```python
    @dachshund.action("ban", label="Ban", confirm=True)
    def ban_user(ctx: dachshund.Context, user_id: str) -> None:
        ...

    dachshund.widget(
        "ban",
        type="button",
        title="Ban a user",
        actions=["ban"],
        action_args={"ban": {"user_id": "42"}},
    )
    ```
    """

    type: ClassVar[str] = "button"
    op: ClassVar[str] = "replace"

    def render(self, events: Sequence[Event]) -> dict[str, Any]:
        """Nothing to show, the card is its actions."""
        return {}

    def update(self, event: Event) -> dict[str, Any] | None:
        """Nothing ever changes."""
        return None
