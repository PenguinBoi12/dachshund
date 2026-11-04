# Button

`Button` is a card with nothing but a title and [action](actions.md) buttons.

```python
import dachshund
from dachshund import Button

@dachshund.action("ban", label="Ban", confirm=True)
def ban(ctx, user_id: str) -> None: ...

with dachshund.row():
    dachshund.add(Button("ban", actions=["ban"], action_args={"ban": {"user_id": "42"}}))
```

::: dachshund.widgets.button.button.Button
