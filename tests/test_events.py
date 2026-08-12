from datetime import datetime, timedelta, timezone

import pytest

from dachshund.storage.events import Event, EventStore


def test_append__expect_the_event_kept_under_its_source() -> None:
    store = EventStore()
    store.append(Event("latency", {"value": 96}))

    assert [event.payload for event in store.events("latency")] == [{"value": 96}]
    assert store.events("other") == []


def test_append_past_the_limit__expect_the_oldest_dropped() -> None:
    store = EventStore(limit=2)

    for value in (1, 2, 3):
        store.append(Event("latency", {"value": value}))

    assert [event.payload["value"] for event in store.events("latency")] == [2, 3]


def test_events__expect_them_oldest_first() -> None:
    store = EventStore()
    now = datetime.now(tz=timezone.utc)

    store.append(Event("latency", at=now - timedelta(minutes=1)))
    store.append(Event("latency", at=now))

    assert [event.at for event in store.events("latency")] == [
        now - timedelta(minutes=1),
        now,
    ]
