import asyncio
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

from dachshund.storage import db

DEFAULT_LIMIT = 500
DEFAULT_PATH = "dachshund.db"

RAW_RETENTION = 1800.0
ROLLUP_BUCKET = 60.0
COMPACT_INTERVAL = 60.0

MIGRATIONS = [
    """
    CREATE TABLE events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        payload TEXT NOT NULL,
        at REAL NOT NULL
    );
    CREATE INDEX idx_events_source_at ON events (source, at);
    """,
    """
    CREATE TABLE event_rollups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        bucket_start REAL NOT NULL,
        payload TEXT NOT NULL,
        count INTEGER NOT NULL,
        UNIQUE (source, bucket_start)
    );
    """,
]


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
        retention: float = RAW_RETENTION,
        bucket: float = ROLLUP_BUCKET,
        compact_interval: float = COMPACT_INTERVAL,
    ) -> None:
        self._connection = connection
        self._executor = executor
        self.limit = limit
        self.retention = retention
        self.bucket = bucket
        self.compact_interval = compact_interval
        self._last_compact = 0.0
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

    async def compact(self) -> None:
        """Fold raw events older than `retention` into rollup buckets.

        A no-op unless `compact_interval` has elapsed since the last call,
        so it's safe to call on every pump tick.

        ## Example

        ```python
        await store.compact()
        ```
        """
        now = time.monotonic()

        if now - self._last_compact < self.compact_interval:
            return

        self._last_compact = now

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._compact)

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
        raw = self._connection.execute(
            "SELECT payload, at FROM events "
            "WHERE source = ? ORDER BY at DESC LIMIT ?",
            (source, self.limit),
        ).fetchall()

        rollups = self._connection.execute(
            "SELECT payload, bucket_start FROM event_rollups "
            "WHERE source = ? ORDER BY bucket_start DESC LIMIT ?",
            (source, self.limit),
        ).fetchall()

        events = [
            Event(
                source, json.loads(payload), datetime.fromtimestamp(at, tz=timezone.utc)
            )
            for payload, at in raw
        ] + [
            Event(
                source,
                json.loads(payload),
                datetime.fromtimestamp(bucket_start + self.bucket / 2, tz=timezone.utc),
            )
            for payload, bucket_start in rollups
        ]
        events.sort(key=lambda event: event.at)

        return events[-self.limit :]

    def _compact(self) -> None:
        boundary = time.time() - self.retention
        cutoff = boundary - (boundary % self.bucket)

        rows = self._connection.execute(
            "SELECT source, payload, at FROM events WHERE at < ?", (cutoff,)
        ).fetchall()

        if not rows:
            return

        buckets: dict[tuple[str, float], list[dict[str, Any]]] = {}

        for source, payload, at in rows:
            bucket_start = at - (at % self.bucket)
            buckets.setdefault((source, bucket_start), []).append(json.loads(payload))

        for (source, bucket_start), payloads in buckets.items():
            payload = _average(payloads)
            count = len(payloads)

            existing = self._connection.execute(
                "SELECT payload, count FROM event_rollups "
                "WHERE source = ? AND bucket_start = ?",
                (source, bucket_start),
            ).fetchone()

            if existing is not None:
                old_payload, old_count = json.loads(existing[0]), existing[1]
                payload = _merge(old_payload, old_count, payload, count)
                count += old_count

            self._connection.execute(
                "INSERT INTO event_rollups (source, bucket_start, payload, count) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT (source, bucket_start) DO UPDATE SET "
                "payload = excluded.payload, count = excluded.count",
                (source, bucket_start, json.dumps(payload), count),
            )

        self._connection.execute("DELETE FROM events WHERE at < ?", (cutoff,))
        self._connection.commit()


def _merge(
    old: dict[str, float], old_count: int, new: dict[str, float], new_count: int
) -> dict[str, float]:
    merged = {}

    for key in old.keys() | new.keys():
        if key not in new:
            merged[key] = old[key]
        elif key not in old:
            merged[key] = new[key]
        else:
            merged[key] = (old[key] * old_count + new[key] * new_count) / (
                old_count + new_count
            )

    return merged


def _average(payloads: Sequence[dict[str, Any]]) -> dict[str, float]:
    from dachshund.widgets.value import numeric

    totals: dict[str, float] = {}
    counts: dict[str, int] = {}

    for payload in payloads:
        for key, raw in payload.items():
            value = numeric(raw)

            if value is None:
                continue

            totals[key] = totals.get(key, 0.0) + value
            counts[key] = counts.get(key, 0) + 1

    return {key: total / counts[key] for key, total in totals.items()}
