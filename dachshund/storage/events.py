import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

from dachshund.storage import db

DEFAULT_LIMIT = 500
DEFAULT_PATH = "dachshund.db"

MIGRATIONS = ["""
    CREATE TABLE events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        payload TEXT NOT NULL,
        at REAL NOT NULL
    );
    CREATE INDEX idx_events_source_at ON events (source, at);
    """]


@dataclass(frozen=True)
class Event:
    """Something that happened in the application.

    ## Example

    ```python
    Event("latency", {"value": 96})
    ```
    """

    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


class EventStore:
    """The recent events of every source, kept in SQLite.

    Every call runs on the single-worker executor its connection belongs to,
    so the same OS thread always owns it, however many stores end up sharing
    the connection.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        executor: ThreadPoolExecutor,
        *,
        limit: int = DEFAULT_LIMIT,
    ) -> None:
        self._connection = connection
        self._executor = executor
        self.limit = limit
        self._closed = False

    def close(self) -> None:
        """Close the connection and stop the executor backing it.

        Safe to call more than once, later calls are a no-op.
        """
        if self._closed:
            return

        self._closed = True
        db.close(self._connection, self._executor)

    async def append(self, events: Sequence[Event]) -> None:
        """Keep a batch of events.

        ## Example

        ```python
        await store.append([Event("latency", {"value": 96})])
        ```
        """
        if not events:
            return

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._insert, events)

    async def events(self, source: str) -> list[Event]:
        """The most recent kept events of a source, up to `limit`, oldest first."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self._select, source)

    def _insert(self, events: Sequence[Event]) -> None:
        rows = [
            (event.source, json.dumps(event.payload), event.at.timestamp())
            for event in events
        ]
        self._connection.executemany(
            "INSERT INTO events (source, payload, at) VALUES (?, ?, ?)", rows
        )
        self._connection.commit()

    def _select(self, source: str) -> list[Event]:
        rows = self._connection.execute(
            "SELECT source, payload, at FROM events "
            "WHERE source = ? ORDER BY at DESC LIMIT ?",
            (source, self.limit),
        ).fetchall()

        events = [
            Event(
                source=row[0],
                payload=json.loads(row[1]),
                at=datetime.fromtimestamp(row[2], tz=timezone.utc),
            )
            for row in rows
        ]
        events.reverse()

        return events
