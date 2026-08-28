# Button

`Button` is a card that's nothing but a title and its action buttons, see [Actions](actions.md). No data of its own.

```python
import dachshund

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

There's no row or event behind a card-level button, so an action needing arguments draws them from `action_args` instead, fixed at registration time rather than per click. See [Actions](actions.md).

::: dachshund.widgets.button.button.Button
