# Actions

An action is a handler the dashboard's UI can invoke. A widget lists the names of its actions; each one renders as a button on the card, and clicking it calls the handler and shows whether it succeeded.

```python
import dachshund

@dachshund.action("block_user", label="Block", confirm=True)
def block_user(user_id: str) -> dict:
    ...

dachshund.widget("last_signup", actions=["block_user"])
```

`label` is what the button shows, falling back to the action's own name. `confirm` asks before running it, off by default.

The handler receives whatever fields of the request's `args` it declares by name; extra fields are ignored, and a missing required one fails the request before the handler runs. A synchronous handler runs off the event loop, so it can block on a database call.

## Host applications with their own event loop

dachshund serves the dashboard on its own event loop, on its own background thread, so an async handler that needs to await something tied to the host application's loop, a Discord bot's HTTP client, for instance, would otherwise run on the wrong loop and fail.

Calling `start()` (directly, or through `init()`) from inside a running event loop keeps that loop as `Dashboard.host_loop`. Every async action handler then runs there instead, so this needs nothing from the handler itself:

```python
@dachshund.action("greet")
async def greet() -> dict:
    channel = bot.get_channel(CHANNEL_ID)
    await channel.send("Hello!")
    return {"sent": True}
```

Starting the dashboard from plain sync code (no running loop at that point) leaves `host_loop` unset, and handlers run on dachshund's own loop, as they always have.

::: dachshund.registry
    options:
      members:
        - action

::: dachshund.actions.Action
