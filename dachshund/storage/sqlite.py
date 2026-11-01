import asyncio
import json
from typing import Any

from dachshund.storage import db

MIGRATIONS = ["""
    CREATE TABLE IF NOT EXISTS widget_state (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """]


class SQLiteStorage:
    """A `Storage` in a SQLite file of its own.

    ## Example

    ```python
    import dachshund
    from dachshund.storage.sqlite import SQLiteStorage

    dachshund.init("Ada", storage=SQLiteStorage("widget_state.db"))
    ```

    ## Options

    - `path` (`str`) - The SQLite file, created if missing. Required.
    """

    def __init__(self, path: str) -> None:
        self._connection, self._executor = db.setup(path, MIGRATIONS)
        self._closed = False

    def close(self) -> None:
        """Close the file. Calling it again does nothing.

        The dashboard never closes a storage, close it when you're done with it.
        """
        if self._closed:
            return

        self._closed = True
        db.close(self._connection, self._executor)

    async def save(self, key: str, value: dict[str, Any]) -> None:
        """Replace whatever was kept under a key."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._save, key, value)

    async def load(self, key: str) -> dict[str, Any] | None:
        """What was last saved under a key, or `None` if nothing was."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._load, key)

    def _save(self, key: str, value: dict[str, Any]) -> None:
        self._connection.execute(
            "INSERT INTO widget_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
        self._connection.commit()

    def _load(self, key: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT value FROM widget_state WHERE key = ?", (key,)
        ).fetchone()

        return json.loads(row[0]) if row is not None else None
