# Actions

An action is a Python function the dashboard calls from a button. A widget lists its actions by name, and each one shows as a button on its card.

```python
import dachshund
from dachshund import Number

@dachshund.action("block_user", label="Block", confirm=True)
def block_user(ctx, user_id: str) -> None: ...

dachshund.add(
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
dachshund.init("Ada", context={"bot": bot})

@dachshund.action("greet")
async def greet(ctx, channel_id: str) -> None:
    await ctx["bot"].get_channel(int(channel_id)).send("Hello!")
```

`ctx` defaults to `{}`. Calling `init()` again merges the new `context` into it.

## Event loop

When `init()` is called from a running event loop, async handlers run on that loop. A bot's client, bound to its own loop, can then be awaited from a handler. Called from sync code, handlers run on dachshund's own loop.

## Result

Whatever a handler returns is sent back as `result` in the response of `POST /_actions/{name}`. Buttons only show whether the call succeeded.

::: dachshund.registry
    options:
      members:
        - action

::: dachshund.actions.Action
