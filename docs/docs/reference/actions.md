# Actions

An action is a handler the dashboard's UI can invoke. A widget lists the names of its actions; each one renders as a button on the card, and clicking it calls the handler and shows whether it succeeded.

```python
import dachshund

@dachshund.action("block_user", label="Block", confirm=True)
def block_user(ctx: dachshund.Context, user_id: str) -> None:
    ...

dachshund.widget(
    "last_signup",
    actions=["block_user"],
    action_args={"block_user": {"user_id": "42"}},
)
```

`label` is what the button shows, falling back to the action's own name. `confirm` asks before running it, off by default.

The handler receives whatever fields of the request's `args` it declares by name, after `ctx` (see [Reaching the host application](#reaching-the-host-application) below); extra fields are ignored, and a missing required one fails the request before the handler runs. A synchronous handler runs off the event loop, so it can block on a database call.

Most handlers return nothing, the UI only shows whether the request succeeded. Whatever a handler does return is carried in the response's `result` field, for a caller hitting `/_actions/{name}` directly rather than through a button.

## Reaching the host application

Every handler's first parameter is always `ctx`, the `dict` passed as `context` to `Dashboard()` or `dachshund.init()`. Put whatever a handler needs from the process embedding dachshund in it, a bot's live client, a database pool, a config object, under whatever keys make sense:

```python
dachshund.init("Ada", context={"bot": bot})

@dachshund.action("greet")
async def greet(ctx: dachshund.Context, channel_id: str) -> None:
    channel = ctx["bot"].get_channel(int(channel_id))
    await channel.send("Hello!")
```

Every action handler must declare `ctx` first, even one that doesn't use it; registering one that doesn't raises immediately. `context` defaults to `{}`, `ctx` is never `None`. Calling `dachshund.init(context=...)` again merges into the existing dict rather than replacing it.

## Supplying arguments

A card-level button, like the `last_signup` one above or a [Button](button.md) widget, has no event or row of its own to draw arguments from, so it needs them fixed at registration time. `action_args` maps an action's name to the arguments its button always sends:

```python
dachshund.widget(
    "last_signup",
    actions=["block_user"],
    action_args={"block_user": {"user_id": "42"}},
)
```

A [Table](table.md)'s row buttons merge `action_args` with the row's own field values, which win on a name collision, for whatever's constant across every row (a guild ID, say) alongside whatever's specific to that row.

## Host applications with their own event loop

dachshund serves the dashboard on its own event loop, on its own background thread, so an async handler that needs to await something tied to the host application's loop, a Discord bot's HTTP client, for instance, would otherwise run on the wrong loop and fail.

Calling `start()` (directly, or through `init()`) from inside a running event loop keeps that loop as `Dashboard.host_loop`. Every async action handler then runs there instead, so this needs nothing from the handler itself:

```python
@dachshund.action("greet")
async def greet(ctx: dachshund.Context) -> None:
    channel = ctx["bot"].get_channel(CHANNEL_ID)
    await channel.send("Hello!")
```

Starting the dashboard from plain sync code (no running loop at that point) leaves `host_loop` unset, and handlers run on dachshund's own loop, as they always have.

::: dachshund.registry
    options:
      members:
        - action

::: dachshund.actions.Action
