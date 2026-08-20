import asyncio
import inspect
from dataclasses import dataclass
from typing import Any, Callable


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

    Raises `TypeError` the same way calling `handler` directly with a
    missing required argument would, without calling it.
    """
    signature = inspect.signature(handler)
    kwargs = {key: value for key, value in args.items() if key in signature.parameters}
    signature.bind(**kwargs)

    return kwargs


async def invoke(
    action: Action,
    kwargs: dict[str, Any],
    host_loop: asyncio.AbstractEventLoop | None = None,
) -> Any:
    """Run `action`'s handler, off the event loop if it isn't a coroutine.

    A coroutine handler runs on `host_loop`, if one is given, instead of
    the loop this is awaited from. See `Dashboard.host_loop`.
    """
    if asyncio.iscoroutinefunction(action.handler):
        coroutine = action.handler(**kwargs)

        if host_loop is not None:
            return await asyncio.wrap_future(
                asyncio.run_coroutine_threadsafe(coroutine, host_loop)
            )

        return await coroutine

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: action.handler(**kwargs))
