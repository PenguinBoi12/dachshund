import asyncio
import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from dachshund.widgets.base import Widget

Context = dict[str, Any]


@dataclass
class Action:
    """A handler the dashboard's UI can invoke.

    ## Example

    ```python
    Action("block_user", block_user, label="Block", confirm=True)
    ```
    """

    name: str
    handler: Callable[..., Any]
    label: str | None = None
    confirm: bool = False


def bind_args(handler: Callable[..., Any], args: dict[str, Any]) -> dict[str, Any]:
    """Filter `args` down to `handler`'s own parameters and validate them.

    Skips `ctx`, `handler`'s first parameter, `invoke()` always supplies it
    separately.

    Raises `TypeError` the same way calling `handler` directly with a
    missing required argument would, without calling it.
    """
    parameters = list(inspect.signature(handler).parameters.values())[1:]
    names = {parameter.name for parameter in parameters}
    kwargs = {key: value for key, value in args.items() if key in names}

    inspect.Signature(parameters).bind(**kwargs)

    return kwargs


async def run(
    func: Callable[..., Any],
    *args: Any,
    host_loop: asyncio.AbstractEventLoop | None = None,
    **kwargs: Any,
) -> Any:
    """Call `func`, off the event loop if it isn't a coroutine.

    A coroutine runs on `host_loop`, if one is given, instead of the loop
    this is awaited from. See `Dashboard.host_loop`.
    """
    if asyncio.iscoroutinefunction(func):
        coroutine = func(*args, **kwargs)

        if host_loop is not None:
            return await asyncio.wrap_future(
                asyncio.run_coroutine_threadsafe(coroutine, host_loop)
            )

        return await coroutine

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


async def invoke(
    action: Action,
    kwargs: dict[str, Any],
    context: Context,
    host_loop: asyncio.AbstractEventLoop | None = None,
) -> Any:
    """Run `action`'s handler. `context` is always its first argument."""
    return await run(action.handler, context, **kwargs, host_loop=host_loop)


def action_card(
    actions: dict[str, Action], name: str, args: dict[str, Any] | None = None
) -> dict[str, Any]:
    """An action, as a card or table row needs it, falling back sensibly if unregistered."""
    action = actions.get(name)

    return {
        "name": name,
        "label": (action.label if action else None) or name,
        "confirm": action.confirm if action else False,
        "args": args or {},
    }


def resolve_row_actions(
    actions: dict[str, Action], widget: "Widget", payload: dict[str, Any]
) -> None:
    """Attach each row's resolved actions, including `action_args`, to a `renders_own_actions` widget's payload, in place."""
    if not widget.renders_own_actions:
        return

    resolved = [
        action_card(actions, name, widget.action_args.get(name)) for name in widget.actions
    ]

    for row in payload.get("rows", []):
        row["actions"] = resolved
