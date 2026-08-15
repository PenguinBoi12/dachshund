from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dachshund.storage import db
from dachshund.storage.events import MIGRATIONS, Event, EventStore


def make_store(path: Path, *, limit: int = 500) -> EventStore:
    connection, executor = db.setup(str(path), MIGRATIONS)

    return EventStore(connection, executor, limit=limit)


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
