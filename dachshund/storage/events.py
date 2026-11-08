import asyncio
import bisect
import json
import logging
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from dachshund.storage import db

DEFAULT_LIMIT = 500
DEFAULT_PATH = "dachshund.db"

RAW_RETENTION = 1800.0
ROLLUP_BUCKET = 60.0
COMPACT_INTERVAL = 60.0
DISTINCT_CAP = 10_000

logger = logging.getLogger("dachshund")

RANKED = (
    "SELECT id, source, ROW_NUMBER() OVER "
    "(PARTITION BY source ORDER BY at DESC, id DESC) AS rank FROM events"
)

MIGRATIONS = [
    """
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        payload TEXT NOT NULL,
        at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_events_source_at ON events (source, at);
    """,
    """
    CREATE TABLE IF NOT EXISTS event_rollups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        bucket_start REAL NOT NULL,
        payload TEXT NOT NULL,
        count INTEGER NOT NULL,
        UNIQUE (source, bucket_start)
    );
    """,
    """
    ALTER TABLE event_rollups ADD COLUMN stats TEXT;
    ALTER TABLE event_rollups ADD COLUMN distinct_values TEXT;
    """,
]

Stats = dict[str, list[float]]
Distinct = dict[str, list[str] | None]


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


@dataclass
class Bucket:
    """What a source's events add up to between two instants, see `EventStore.summarize`."""

    start: float
    count: int = 0
    values: int = 0
    sum: float = 0.0
    min: float | None = None
    max: float | None = None
    distinct: set[str] | None = None

    def add(
        self,
        count: int,
        values: int,
        total: float,
        low: float | None,
        high: float | None,
    ) -> None:
        self.count += count
        self.values += values
        self.sum += total

        if low is not None:
            self.min = low if self.min is None else min(self.min, low)

        if high is not None:
            self.max = high if self.max is None else max(self.max, high)


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
        self._last_compact = float("-inf")
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

    async def events(
        self, source: str, *, rollups: bool = True, limit: int | None = None
    ) -> list[Event]:
        """The most recent kept events of a source, up to `limit`, oldest first.

        With `rollups`, events older than `retention` come back as one averaged
        event per bucket. Without, only raw events are read. `limit` defaults
        to the store's.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, self._select, source, rollups, limit or self.limit
        )

    async def summarize(
        self,
        source: str,
        field: str,
        *,
        boundaries: Sequence[float],
        distinct: bool = False,
    ) -> list[Bucket]:
        """What `source`'s events add up to between each pair of `boundaries`.

        One bucket per `[boundaries[i], boundaries[i + 1])`, oldest first:
        how many events, and the count, sum, min and max of `field`'s numbers.
        With `distinct`, also `field`'s distinct values, `None` where they
        weren't kept. Exact over raw events. Over older ones, a rollup bucket the
        window starts in counts in full.

        ## Example

        ```python
        [bucket] = await store.summarize("requests", "ms", boundaries=[since, now])
        bucket.count, bucket.sum / bucket.values
        ```
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, self._summarize, source, field, boundaries, distinct
        )

    async def compact(
        self,
        distinct_fields: Mapping[str, set[str]] | None = None,
        keep: Mapping[str, int] | None = None,
    ) -> None:
        """Fold raw events older than `retention` into rollup buckets.

        A bucket keeps how many events it holds and, for each numeric field,
        the count, sum, min and max of its values. `distinct_fields` names, by
        source, the fields whose distinct values are kept too, up to
        `DISTINCT_CAP` per bucket.

        Each source's newest `keep` events, 1 for a source it doesn't name, are
        always kept raw, so a widget showing the latest value never loses it,
        however rarely its source emits.

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
        await loop.run_in_executor(
            self._executor, self._compact, dict(distinct_fields or {}), dict(keep or {})
        )

    def _insert(self, events: Sequence[Event]) -> None:
        rows = [
            (event.source, json.dumps(event.payload), event.at.timestamp())
            for event in events
        ]
        self._connection.executemany(
            "INSERT INTO events (source, payload, at) VALUES (?, ?, ?)", rows
        )
        self._connection.commit()

    def _select(
        self, source: str, rollups: bool = True, limit: int | None = None
    ) -> list[Event]:
        limit = limit or self.limit

        raw = self._connection.execute(
            "SELECT payload, at FROM events "
            "WHERE source = ? ORDER BY at DESC, id DESC LIMIT ?",
            (source, limit),
        ).fetchall()

        averaged = (
            self._connection.execute(
                "SELECT payload, bucket_start FROM event_rollups "
                "WHERE source = ? ORDER BY bucket_start DESC LIMIT ?",
                (source, limit),
            ).fetchall()
            if rollups
            else []
        )

        events = [
            Event(
                source, json.loads(payload), datetime.fromtimestamp(at, tz=timezone.utc)
            )
            for payload, at in reversed(raw)
        ] + [
            Event(
                source,
                json.loads(payload),
                datetime.fromtimestamp(bucket_start + self.bucket / 2, tz=timezone.utc),
            )
            for payload, bucket_start in averaged
        ]
        events.sort(key=lambda event: event.at)

        return events[-limit:]

    def _compact(
        self, distinct_fields: dict[str, set[str]], keep: dict[str, int] | None = None
    ) -> None:
        boundary = time.time() - self.retention
        cutoff = boundary - (boundary % self.bucket)
        self._keep_newest(keep or {})

        rows = self._connection.execute(
            "SELECT source, payload, at FROM events "
            "WHERE at < ? AND id NOT IN (SELECT id FROM kept)",
            (cutoff,),
        ).fetchall()

        if not rows:
            return

        buckets: dict[tuple[str, float], list[dict[str, Any]]] = {}

        for source, payload, at in rows:
            bucket_start = at - (at % self.bucket)
            buckets.setdefault((source, bucket_start), []).append(json.loads(payload))

        for (source, bucket_start), payloads in buckets.items():
            stats = _stats(payloads)
            distinct = _distinct(payloads, distinct_fields.get(source, set()))
            count = len(payloads)

            existing = self._connection.execute(
                "SELECT payload, count, stats, distinct_values FROM event_rollups "
                "WHERE source = ? AND bucket_start = ?",
                (source, bucket_start),
            ).fetchone()

            if existing is not None:
                old_payload, old_count, old_stats, old_distinct = existing
                stats = _merge_stats(
                    _stored_stats(old_payload, old_count, old_stats), stats
                )
                distinct = _merge_distinct(json.loads(old_distinct or "{}"), distinct)
                count += old_count

            averages = {key: total / n for key, (n, total, _, _) in stats.items()}

            self._connection.execute(
                "INSERT INTO event_rollups "
                "(source, bucket_start, payload, count, stats, distinct_values) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (source, bucket_start) DO UPDATE SET "
                "payload = excluded.payload, count = excluded.count, "
                "stats = excluded.stats, distinct_values = excluded.distinct_values",
                (
                    source,
                    bucket_start,
                    json.dumps(averages),
                    count,
                    json.dumps(stats),
                    json.dumps(distinct),
                ),
            )

        self._connection.execute(
            "DELETE FROM events WHERE at < ? AND id NOT IN (SELECT id FROM kept)",
            (cutoff,),
        )
        self._connection.commit()

    def _keep_newest(self, keep: dict[str, int]) -> None:
        """Fill the `kept` temp table with each source's newest `keep` raw event ids."""
        self._connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS kept (id INTEGER PRIMARY KEY)"
        )
        self._connection.execute("DELETE FROM kept")

        ranked = self._connection.execute(
            f"SELECT id, source, rank FROM ({RANKED}) WHERE rank <= ?",
            (max(keep.values(), default=1),),
        ).fetchall()

        self._connection.executemany(
            "INSERT INTO kept (id) VALUES (?)",
            [(id,) for id, source, rank in ranked if rank <= keep.get(source, 1)],
        )

    def _summarize(
        self,
        source: str,
        field: str,
        boundaries: Sequence[float],
        distinct: bool,
    ) -> list[Bucket]:
        edges = list(boundaries)
        buckets = [
            Bucket(start, distinct=set() if distinct else None) for start in edges[:-1]
        ]

        if not buckets:
            return []

        def bucket_at(at: float) -> Bucket:
            return buckets[max(0, bisect.bisect_right(edges, at) - 1)]

        raw = self._connection.execute(
            "SELECT at, payload FROM events WHERE source = ? AND at >= ? AND at < ?",
            (source, edges[0], edges[-1]),
        ).fetchall()

        for at, payload in raw:
            value = json.loads(payload).get(field)
            number = _number(value)
            bucket = bucket_at(at)
            bucket.add(1, number is not None, number or 0.0, number, number)

            if bucket.distinct is not None and value is not None:
                bucket.distinct.add(_label(value))

        rollups = self._connection.execute(
            "SELECT bucket_start, payload, count, stats, distinct_values "
            "FROM event_rollups "
            "WHERE source = ? AND bucket_start > ? AND bucket_start < ?",
            (source, edges[0] - self.bucket, edges[-1]),
        ).fetchall()

        for bucket_start, payload, count, stats, distinct_values in rollups:
            bucket = bucket_at(bucket_start)
            kept = _stored_stats(payload, count, stats).get(field)

            if kept is None:
                bucket.add(count, 0, 0.0, None, None)
            else:
                n, total, low, high = kept
                bucket.add(count, int(n), total, low, high)

            if bucket.distinct is not None:
                labels = json.loads(distinct_values or "{}").get(field)
                bucket.distinct = (
                    None if labels is None else bucket.distinct | set(labels)
                )

        return buckets


def _number(value: Any) -> float | None:
    from dachshund.widgets.value import numeric

    return numeric(value)


def _label(value: Any) -> str:
    """A value as distinct counting compares it."""
    return value if isinstance(value, str) else json.dumps(value)


def _stats(payloads: Sequence[dict[str, Any]]) -> Stats:
    stats: Stats = {}

    for payload in payloads:
        for key, raw in payload.items():
            value = _number(raw)

            if value is None:
                continue

            if key in stats:
                n, total, low, high = stats[key]
                stats[key] = [n + 1, total + value, min(low, value), max(high, value)]
            else:
                stats[key] = [1, value, value, value]

    return stats


def _merge_stats(old: Stats, new: Stats) -> Stats:
    merged = dict(old)

    for key, (n, total, low, high) in new.items():
        if key in merged:
            old_n, old_total, old_low, old_high = merged[key]
            merged[key] = [
                old_n + n,
                old_total + total,
                min(old_low, low),
                max(old_high, high),
            ]
        else:
            merged[key] = [n, total, low, high]

    return merged


def _stored_stats(payload: str, count: int, stats: str | None) -> Stats:
    """A rollup's stats, read from its averages for a row older than them."""
    if stats is not None:
        kept: Stats = json.loads(stats)
        return kept

    return {
        key: [count, average * count, average, average]
        for key, average in json.loads(payload).items()
    }


def _distinct(payloads: Sequence[dict[str, Any]], fields: set[str]) -> Distinct:
    found: dict[str, set[str]] = {key: set() for key in fields}

    for payload in payloads:
        for key in fields:
            if payload.get(key) is not None:
                found[key].add(_label(payload[key]))

    return {key: _capped(key, labels) for key, labels in found.items()}


def _merge_distinct(old: Distinct, new: Distinct) -> Distinct:
    merged = dict(old)

    for key, labels in new.items():
        if key not in merged:
            merged[key] = labels
        elif merged[key] is None or labels is None:
            merged[key] = None
        else:
            merged[key] = _capped(key, set(merged[key] or []) | set(labels))

    return merged


def _capped(key: str, labels: set[str]) -> list[str] | None:
    if len(labels) > DISTINCT_CAP:
        logger.warning(
            "%r has over %d distinct values in a minute, its distinct count "
            "isn't kept for that minute.",
            key,
            DISTINCT_CAP,
        )
        return None

    return sorted(labels)
