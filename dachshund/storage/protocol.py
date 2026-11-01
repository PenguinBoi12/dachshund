import asyncio
from typing import Any, Protocol


class Storage(Protocol):
    """Where persisted widget state is saved.

    A backend maps a key to a JSON-shaped dict, through two async methods:
    `save(key, value)` and `load(key)`, which returns `None` for an unknown
    key. See the [Persistent Storage](../guides/persistent-storage.md) guide.

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
    """A `Storage` for a backend with synchronous calls, such as an ORM.

    Subclass and write `_save(key, value)` and `_load(key)`. Each call runs in
    a thread, off the event loop, so the backend must be safe to call from any
    thread.

    ## Example

    ```python
    from dachshund.storage.protocol import SyncStorage

    class FileStorage(SyncStorage):
        def __init__(self, path: str) -> None:
            self.path = path

        def _save(self, key, value): ...

        def _load(self, key): ...
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
