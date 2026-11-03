# Actions

An action is a Python function the dashboard calls from a button. A widget lists its actions by name, and each one shows as a button on its card.

```python
import dachshund
from dachshund import Number

@dachshund.action("block_user", label="Block", confirm=True)
def block_user(ctx, user_id: str) -> None: ...

dachshund.row(
    Number(
        "last_signup",
        actions=["block_user"],
        action_args={"block_user": {"user_id": "42"}},
    )
)
```

## Arguments

A handler receives the arguments it declares after `ctx`, by name. Extra ones are ignored, and a missing required one fails the call before the handler runs.

- On a card, arguments come from the widget's `action_args`.
- On a [Table](table.md) row, they come from the row's fields merged over `action_args`.

A handler can be sync or async. A sync handler runs in a thread, so it can block.

## Context

`ctx` is the `context` given to `dachshund.init()`. Put whatever a handler needs from your application in it.

```python
dachshund.init("My service", context={"db": db})

@dachshund.action("deactivate")
async def deactivate(ctx, user_id: str) -> None:
    await ctx["db"].deactivate_user(int(user_id))
```

`ctx` defaults to `{}`. Calling `init()` again merges the new `context` into it.

## Event loop

When `init()` is called from a running event loop, async handlers run on that loop. A client bound to your application's loop, such as a database pool, can then be awaited from a handler. Called from sync code, handlers run on dachshund's own loop.

## Result

Whatever a handler returns is sent back as `result` in the response of `POST /_actions/{name}`. Buttons only show whether the call succeeded.

::: dachshund.registry
    options:
      members:
        - action

::: dachshund.actions.Action
