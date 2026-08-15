from typing import Any, Protocol


class Storage(Protocol):
    """Wherever a widget's persisted state lives.

    Deliberately dumb: a key to a JSON-shaped value, nothing to query, no
    increment. That's what makes a backend easy to write, SQLite, Redis, a
    flat file, anything that can get and set a key qualifies.

    ## Example

    ```python
    import dachshund

    dachshund.init("Ada", storage=MyStorage())
    ```
    """

    async def save(self, key: str, value: dict[str, Any]) -> None:
        """Replace whatever was kept under a key."""
        ...

    async def load(self, key: str) -> dict[str, Any] | None:
        """What was last saved under a key, or `None` if nothing was."""
        ...
