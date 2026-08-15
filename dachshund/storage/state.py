import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from dachshund.storage import db

MIGRATIONS = ["""
    CREATE TABLE widget_state (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """]


class SQLiteStorage:
    """A `Storage` backed by its own SQLite file.

    Self-contained: give it a path and it owns its own connection and
    single-worker executor, entirely separate from whatever database a
    dashboard's raw events live in.

    ## Example

    ```python
    import dachshund
    from dachshund.storage.state import SQLiteStorage

    dachshund.init("Ada", storage=SQLiteStorage("widget_state.db"))
    ```
    """

    def __init__(self, path: str) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._connection = self._executor.submit(db.connect, path).result()
        self._executor.submit(db.migrate, self._connection, MIGRATIONS).result()

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
