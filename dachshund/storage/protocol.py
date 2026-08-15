import asyncio
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


class SyncStorage:
    """A `Storage` for a backend whose save/load are plain synchronous calls.

    Subclass and implement `_save`/`_load`; `asyncio.to_thread` runs each
    off the event loop. Good for a backend that's safe to call from any
    thread, an ORM session, a synchronous driver. `SQLiteStorage` pins its
    connection to one thread instead, so it doesn't use this.

    ## Example

    ```python
    from dachshund.storage.protocol import SyncStorage

    class FileStorage(SyncStorage):
        def __init__(self, path: str) -> None:
            self.path = path

        def _save(self, key, value):
            ...

        def _load(self, key):
            ...
    ```
    """

    async def save(self, key: str, value: dict[str, Any]) -> None:
        """Replace whatever was kept under a key."""
        await asyncio.to_thread(self._save, key, value)

    async def load(self, key: str) -> dict[str, Any] | None:
        """What was last saved under a key, or `None` if nothing was."""
        return await asyncio.to_thread(self._load, key)

    def _save(self, key: str, value: dict[str, Any]) -> None:
        raise NotImplementedError

    def _load(self, key: str) -> dict[str, Any] | None:
        raise NotImplementedError
