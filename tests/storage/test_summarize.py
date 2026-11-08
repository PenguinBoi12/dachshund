import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dachshund.storage import db, events
from dachshund.storage.events import MIGRATIONS, Event, EventStore


def make_store(path: Path, *, retention: float = 0.0) -> EventStore:
    connection, executor = db.setup(str(path), MIGRATIONS)

    return EventStore(connection, executor, retention=retention, compact_interval=0.0)


def minute_ago(minutes: int, second: int = 0) -> float:
    """The start of the minute `minutes` ago, plus `second`."""
    now = time.time()
    return now - (now % 60) - minutes * 60 + second


def at(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def rollups(path: Path) -> list[tuple]:
    return (
        db.connect(str(path))
        .execute("SELECT source, count, stats, distinct_values FROM event_rollups")
        .fetchall()
    )


@pytest.mark.asyncio
async def test_compact__expect_exact_count_sum_min_max_per_field(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path / "events.db")
    start = minute_ago(10)

    await store.append(
        [
            Event("latency", {"ms": 10, "label": "ok"}, at=at(start + 1)),
            Event("latency", {"ms": 30}, at=at(start + 2)),
            Event("latency", {"ms": "20"}, at=at(start + 3)),
            Event("latency", {"ms": 99}),
        ]
    )
    await store.compact()

    [(source, count, stats, distinct)] = rollups(tmp_path / "events.db")

    assert (source, count) == ("latency", 3)
    assert json.loads(stats) == {"ms": [3, 60.0, 10.0, 30.0]}
    assert json.loads(distinct) == {}


@pytest.mark.asyncio
async def test_compact_of_a_non_numeric_source__expect_it_rolled_up_too(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path / "events.db")

    await store.append(
        [
            Event("sessions", {"user": "ada"}, at=at(minute_ago(10, 1))),
            Event("sessions", {"user": "grace"}),
        ]
    )
    await store.compact()

    assert rollups(tmp_path / "events.db") == [("sessions", 1, "{}", "{}")]


@pytest.mark.asyncio
async def test_compact_with_distinct_fields__expect_values_kept_for_those_only(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path / "events.db")
    start = minute_ago(10)

    await store.append(
        [
            Event("messages", {"author": "ada", "room": 1}, at=at(start + 1)),
            Event("messages", {"author": "ada", "room": 2}, at=at(start + 2)),
            Event("messages", {"author": 42, "room": 2}, at=at(start + 3)),
            Event("messages", {"author": "grace"}),
        ]
    )
    await store.compact({"messages": {"author"}})

    [(_, _, _, distinct)] = rollups(tmp_path / "events.db")

    assert json.loads(distinct) == {"author": ["42", "ada"]}


@pytest.mark.asyncio
async def test_compact_over_the_distinct_cap__expect_none_and_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(events, "DISTINCT_CAP", 2)
    store = make_store(tmp_path / "events.db")
    start = minute_ago(10)

    await store.append(
        [Event("messages", {"author": name}, at=at(start + 1)) for name in "abc"]
        + [Event("messages", {"author": "z"})]
    )

    with caplog.at_level(logging.WARNING, logger="dachshund"):
        await store.compact({"messages": {"author"}})

    [(_, _, _, distinct)] = rollups(tmp_path / "events.db")

    assert json.loads(distinct) == {"author": None}
    assert "distinct" in caplog.text


@pytest.mark.asyncio
async def test_compact_into_an_existing_bucket__expect_stats_and_distinct_merged(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path / "events.db")
    start = minute_ago(10)

    await store.append([Event("m", {"ms": 10, "a": "x"}, at=at(start + 1))])
    await store.append([Event("m", {"ms": 1})])
    await store.compact({"m": {"a"}})
    await store.append([Event("m", {"ms": 30, "a": "y"}, at=at(start + 2))])
    await store.append([Event("m", {"ms": 2})])
    await store.compact({"m": {"a"}})

    rows = (
        db.connect(str(tmp_path / "events.db"))
        .execute(
            "SELECT count, stats, distinct_values, payload FROM event_rollups "
            "WHERE bucket_start = ?",
            (start,),
        )
        .fetchall()
    )
    [(count, stats, distinct, payload)] = rows

    assert count == 2
    assert json.loads(stats)["ms"] == [2, 40.0, 10.0, 30.0]
    assert json.loads(distinct) == {"a": ["x", "y"]}
    assert json.loads(payload)["ms"] == 20.0


@pytest.mark.asyncio
async def test_summarize_of_a_rollup_older_than_its_stats__expect_them_read_from_the_average(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.db"
    store = make_store(path)
    start = minute_ago(10)
    seed = db.connect(str(path))
    seed.execute(
        "INSERT INTO event_rollups (source, bucket_start, payload, count) "
        "VALUES (?, ?, ?, ?)",
        ("latency", start, json.dumps({"ms": 15.0}), 4),
    )
    seed.commit()

    [bucket] = await store.summarize("latency", "ms", boundaries=[start, time.time()])

    assert (bucket.count, bucket.values, bucket.sum) == (4, 4, 60.0)
    assert (bucket.min, bucket.max) == (15.0, 15.0)


@pytest.mark.asyncio
async def test_events_without_rollups__expect_raw_events_only(tmp_path: Path) -> None:
    store = make_store(tmp_path / "events.db")

    await store.append(
        [
            Event("latency", {"ms": 10}, at=at(minute_ago(10, 1))),
            Event("latency", {"ms": 2}),
        ]
    )
    await store.compact()

    with_rollups = await store.events("latency")
    raw = await store.events("latency", rollups=False)

    assert [event.payload for event in with_rollups] == [{"ms": 10.0}, {"ms": 2}]
    assert [event.payload for event in raw] == [{"ms": 2}]


@pytest.mark.asyncio
async def test_summarize_across_rollups_and_raw__expect_one_exact_bucket(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path / "events.db", retention=0.0)
    old = minute_ago(10)

    await store.append(
        [
            Event("latency", {"ms": 10, "user": "ada"}, at=at(old + 1)),
            Event("latency", {"ms": 50, "user": "bob"}, at=at(old + 2)),
            Event("latency", {"user": "cy"}, at=at(old + 3)),
            Event("latency", {"ms": 5, "user": "ada"}),
        ]
    )
    await store.compact({"latency": {"user"}})

    [bucket] = await store.summarize(
        "latency", "ms", boundaries=[old - 60, time.time() + 1]
    )
    [users] = await store.summarize(
        "latency", "user", boundaries=[old - 60, time.time() + 1], distinct=True
    )

    assert (bucket.count, bucket.values, bucket.sum) == (4, 3, 65.0)
    assert (bucket.min, bucket.max) == (5.0, 50.0)
    assert users.distinct == {"ada", "bob", "cy"}


@pytest.mark.asyncio
async def test_summarize_with_boundaries__expect_events_in_their_bucket(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path / "events.db", retention=3600.0)
    start = minute_ago(3)

    await store.append(
        [
            Event("requests", {}, at=at(start - 30)),
            Event("requests", {}, at=at(start + 10)),
            Event("requests", {}, at=at(start + 70)),
            Event("requests", {}, at=at(start + 80)),
        ]
    )

    buckets = await store.summarize(
        "requests", "value", boundaries=[start, start + 60, start + 120]
    )

    assert [bucket.start for bucket in buckets] == [start, start + 60]
    assert [bucket.count for bucket in buckets] == [1, 2]
    assert [bucket.values for bucket in buckets] == [0, 0]


@pytest.mark.asyncio
async def test_summarize_distinct_over_an_untracked_rollup__expect_none(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path / "events.db")
    old = minute_ago(10)

    await store.append(
        [Event("messages", {"author": "ada"}, at=at(old + 1)), Event("messages", {})]
    )
    await store.compact()

    [bucket] = await store.summarize(
        "messages", "author", boundaries=[old, time.time() + 1], distinct=True
    )

    assert bucket.distinct is None


@pytest.mark.asyncio
async def test_summarize_without_boundaries__expect_no_bucket(tmp_path: Path) -> None:
    store = make_store(tmp_path / "events.db")

    assert await store.summarize("requests", "value", boundaries=[time.time()]) == []


@pytest.mark.asyncio
async def test_summarize_from_mid_bucket__expect_the_overlapping_rollup_counted(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path / "events.db")
    old = minute_ago(10)

    await store.append(
        [
            Event("requests", {}, at=at(old + 40)),
            Event("requests", {}, at=at(old + 50)),
            Event("requests", {}),
        ]
    )
    await store.compact()

    [bucket] = await store.summarize(
        "requests", "value", boundaries=[old + 30, time.time() + 1]
    )

    assert bucket.count == 3


@pytest.mark.asyncio
async def test_compact_with_keep__expect_the_newest_n_raw_and_the_rest_rolled_up(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path / "events.db")
    old = minute_ago(10)

    await store.append(
        [Event("logs", {"n": n}, at=at(old + n)) for n in range(5)]
        + [Event("latency", {"n": n}, at=at(old + n)) for n in range(3)]
    )
    await store.compact(keep={"logs": 3})

    logs = await store.events("logs", rollups=False)
    latency = await store.events("latency", rollups=False)
    rolled = dict(
        db.connect(str(tmp_path / "events.db"))
        .execute("SELECT source, count FROM event_rollups")
        .fetchall()
    )

    assert [event.payload["n"] for event in logs] == [2, 3, 4]
    assert [event.payload["n"] for event in latency] == [2]
    assert rolled == {"logs": 2, "latency": 2}


@pytest.mark.asyncio
async def test_events_with_a_limit__expect_that_many(tmp_path: Path) -> None:
    store = make_store(tmp_path / "events.db", retention=3600.0)

    await store.append([Event("logs", {"n": n}) for n in range(5)])

    assert [e.payload["n"] for e in await store.events("logs", limit=2)] == [3, 4]
