import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dachshund.storage import db
from dachshund.storage.events import (
    COMPACT_INTERVAL,
    MIGRATIONS,
    ROLLUP_BUCKET,
    Event,
    EventStore,
)


def make_store(
    path: Path,
    *,
    limit: int = 500,
    retention: float = 1800.0,
    bucket: float = ROLLUP_BUCKET,
    compact_interval: float = COMPACT_INTERVAL,
) -> EventStore:
    connection, executor = db.setup(str(path), MIGRATIONS)

    return EventStore(
        connection,
        executor,
        limit=limit,
        retention=retention,
        bucket=bucket,
        compact_interval=compact_interval,
    )


@pytest.fixture
def store(tmp_path: Path) -> EventStore:
    return make_store(tmp_path / "events.db")


@pytest.mark.asyncio
async def test_append_then_events__expect_the_payload_round_tripped(
    store: EventStore,
) -> None:
    await store.append([Event("latency", {"value": 96})])

    events = await store.events("latency")

    assert [event.payload for event in events] == [{"value": 96}]


@pytest.mark.asyncio
async def test_events_of_an_unknown_source__expect_nothing(store: EventStore) -> None:
    assert await store.events("other") == []


@pytest.mark.asyncio
async def test_events_of_two_sources__expect_them_kept_apart(
    store: EventStore,
) -> None:
    await store.append([Event("latency", {"value": 1}), Event("errors", {"value": 2})])

    assert [e.payload for e in await store.events("latency")] == [{"value": 1}]
    assert [e.payload for e in await store.events("errors")] == [{"value": 2}]


@pytest.mark.asyncio
async def test_events__expect_them_oldest_first(store: EventStore) -> None:
    now = datetime.now(tz=timezone.utc)

    await store.append(
        [
            Event("latency", at=now),
            Event("latency", at=now - timedelta(minutes=1)),
        ]
    )

    events = await store.events("latency")

    assert [event.at for event in events] == [
        now - timedelta(minutes=1),
        now,
    ]


@pytest.mark.asyncio
async def test_append_past_the_limit__expect_the_oldest_dropped_on_read(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path / "events.db", limit=2)

    await store.append([Event("latency", {"value": value}) for value in (1, 2, 3)])

    events = await store.events("latency")

    assert [event.payload["value"] for event in events] == [2, 3]


@pytest.mark.asyncio
async def test_append_of_nothing__expect_no_error(store: EventStore) -> None:
    await store.append([])

    assert await store.events("latency") == []


@pytest.mark.asyncio
async def test_close_then_use__expect_an_error(store: EventStore) -> None:
    store.close()

    with pytest.raises(RuntimeError):
        await store.append([Event("latency", {"value": 1})])


def test_close_twice__expect_no_error(store: EventStore) -> None:
    store.close()
    store.close()


@pytest.mark.asyncio
async def test_a_second_connection_to_the_same_file__expect_the_events_kept(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.db"
    store = make_store(path)

    await store.append([Event("latency", {"value": 96})])

    reopened = db.connect(str(path))
    row = reopened.execute(
        "SELECT source, payload FROM events WHERE source = ?", ("latency",)
    ).fetchone()

    assert row is not None
    assert row[0] == "latency"


@pytest.mark.asyncio
async def test_compact_of_old_events__expect_the_raw_rows_deleted_and_a_rollup_row_inserted(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.db"
    store = make_store(path, retention=0.0)
    old = datetime.now(tz=timezone.utc) - timedelta(seconds=1)

    await store.append([Event("latency", {"value": 10}, at=old)])
    await store.compact()

    reopened = db.connect(str(path))
    raw = reopened.execute("SELECT * FROM events").fetchall()
    rollups = reopened.execute(
        "SELECT source, payload, count FROM event_rollups"
    ).fetchall()

    assert raw == []
    assert rollups == [("latency", json.dumps({"value": 10.0}), 1)]


@pytest.mark.asyncio
async def test_compact__expect_the_rollup_payload_averaged(tmp_path: Path) -> None:
    path = tmp_path / "events.db"
    store = make_store(path, retention=0.0)
    old = datetime.now(tz=timezone.utc) - timedelta(seconds=1)

    await store.append(
        [
            Event("latency", {"value": 10}, at=old),
            Event("latency", {"value": 20}, at=old),
        ]
    )
    await store.compact()

    reopened = db.connect(str(path))
    rollups = reopened.execute("SELECT payload, count FROM event_rollups").fetchall()

    assert rollups == [(json.dumps({"value": 15.0}), 2)]


@pytest.mark.asyncio
async def test_compact_with_a_non_numeric_field__expect_it_dropped(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.db"
    store = make_store(path, retention=0.0)
    old = datetime.now(tz=timezone.utc) - timedelta(seconds=1)

    await store.append([Event("latency", {"value": 10, "label": "ok"}, at=old)])
    await store.compact()

    reopened = db.connect(str(path))
    payload = reopened.execute("SELECT payload FROM event_rollups").fetchone()[0]

    assert json.loads(payload) == {"value": 10.0}


@pytest.mark.asyncio
async def test_compact_before_the_interval_elapses__expect_the_second_call_a_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = make_store(tmp_path / "events.db", retention=0.0)
    calls = []
    monkeypatch.setattr(store, "_compact", lambda: calls.append(None))

    await store.compact()
    await store.compact()

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_events_after_compaction__expect_raw_and_rollup_merged_oldest_first(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path / "events.db", retention=0.0)
    now = datetime.now(tz=timezone.utc)
    old = now - timedelta(minutes=5)

    await store.append([Event("latency", {"value": 1}, at=old)])
    await store.compact()
    await store.append([Event("latency", {"value": 2}, at=now)])

    events = await store.events("latency")

    assert [event.payload for event in events] == [{"value": 1.0}, {"value": 2}]


@pytest.mark.asyncio
async def test_events_when_raw_alone_fills_the_limit__expect_rollups_untouched(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path / "events.db", limit=2)

    await store.append([Event("latency", {"value": value}) for value in (1, 2, 3)])

    events = await store.events("latency")

    assert [event.payload["value"] for event in events] == [2, 3]
