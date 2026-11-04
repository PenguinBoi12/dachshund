from dataclasses import dataclass
from typing import Any, ClassVar, Sequence

from dachshund.storage.events import Event
from dachshund.widgets.base import Widget


@dataclass
class Button(Widget):
    """A card with nothing but a title and action buttons.

    ## Example

    ```python
    @dachshund.action("ban", label="Ban", confirm=True)
    def ban(ctx, user_id: str) -> None: ...

    with dachshund.row():
        dachshund.add(
            Button(
                "ban",
                title="Ban a user",
                actions=["ban"],
                action_args={"ban": {"user_id": "42"}},
            )
        )
    ```

    ## Options

    - `actions` (`list[str]`) - The actions shown as buttons. Defaults to `[]`.
    - `action_args` (`dict[str, dict]`) - The arguments each action is called
      with, by action name. Defaults to `{}`.

    A button has no event or row behind it, so `action_args` is the only way
    to pass an action arguments.
    """

    type: ClassVar[str] = "button"
    op: ClassVar[str] = "replace"

    def render(self, events: Sequence[Event]) -> dict[str, Any]:
        """Nothing to show, the card is its actions."""
        return {}

    def update(self, event: Event) -> dict[str, Any] | None:
        """Nothing ever changes."""
        return None
