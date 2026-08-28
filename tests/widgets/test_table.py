import asyncio
import logging
import threading
from datetime import datetime, timezone

import pytest

from dachshund.storage.events import Event
from dachshund.widgets.table.table import Table


def test_table_type_and_op__expect_a_full_replace() -> None:
    assert (Table.type, Table.op) == ("table", "replace")


def test_table_renders_own_actions__expect_it_true() -> None:
    assert Table.renders_own_actions is True


def test_table_script_and_style__expect_them_set() -> None:
    assert Table.script is not None and Table.script.is_file()
    assert Table.style is not None and Table.style.is_file()


def test_table_render__expect_a_row_per_event() -> None:
    table = Table("sessions", source="sessions", columns=["user", "ip"])
    events = [
        Event("sessions", {"user": "ada", "ip": "10.0.0.1"}),
        Event("sessions", {"user": "bob", "ip": "10.0.0.2"}),
    ]

    assert table.render(events) == {
        "columns": ["user", "ip"],
        "rows": [
            {"fields": {"user": "ada", "ip": "10.0.0.1"}},
            {"fields": {"user": "bob", "ip": "10.0.0.2"}},
        ],
    }


def test_table_render_with_a_hidden_column__expect_it_off_the_shown_list() -> None:
    table = Table("members", source="members", columns=["id", "name", "_guild_id"])

    payload = table.render(
        [Event("members", {"id": "1", "name": "ada", "guild_id": 42})]
    )

    assert payload["columns"] == ["id", "name"]
    assert payload["rows"][0]["fields"] == {"id": "1", "name": "ada", "guild_id": 42}


def test_table_render_with_an_underscored_field__expect_it_stripped() -> None:
    table = Table("members", source="members", columns=["id", "name"])

    payload = table.render(
        [Event("members", {"id": "1", "name": "ada", "_guild_id": 42})]
    )

    assert payload["rows"][0]["fields"] == {"id": "1", "name": "ada", "guild_id": 42}


def test_table_render_without_a_key__expect_no_dedup() -> None:
    table = Table("sessions", source="sessions", columns=["user"])
    events = [
        Event("sessions", {"user": "ada"}),
        Event("sessions", {"user": "ada"}),
    ]

    assert len(table.render(events)["rows"]) == 2


def test_table_render_with_a_key__expect_a_repeated_row_replaced() -> None:
    table = Table("sessions", source="sessions", columns=["user", "ip"], key="user")
    events = [
        Event("sessions", {"user": "ada", "ip": "10.0.0.1"}),
        Event("sessions", {"user": "bob", "ip": "10.0.0.2"}),
        Event("sessions", {"user": "ada", "ip": "10.0.0.9"}),
    ]

    assert table.render(events) == {
        "columns": ["user", "ip"],
        "rows": [
            {"fields": {"user": "ada", "ip": "10.0.0.9"}},
            {"fields": {"user": "bob", "ip": "10.0.0.2"}},
        ],
    }


def test_table_render_with_a_key_missing_from_an_event__expect_its_own_row() -> None:
    table = Table("sessions", source="sessions", columns=["user"], key="user")
    events = [
        Event("sessions", {}),
        Event("sessions", {}),
    ]

    assert len(table.render(events)["rows"]) == 2


def test_table_render_with_delete_and_no_persist__expect_no_delete_field() -> None:
    table = Table("sessions", source="sessions", columns=["user", "ip"], key="user")
    events = [
        Event("sessions", {"user": "ada", "ip": "10.0.0.1"}),
        Event("sessions", {"user": "ada", "_delete": True}),
    ]

    assert table.render(events)["rows"] == [{"fields": {"user": "ada"}}]


def _at(seconds: float) -> datetime:
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def test_table_with_persist_and_no_key__expect_value_error() -> None:
    with pytest.raises(ValueError, match="no key to identify a row by"):
        Table("sessions", source="sessions", columns=["user"], persist=True)


def test_table_accumulate_without_persist__expect_nothing_kept() -> None:
    table = Table("sessions", source="sessions", columns=["user"], key="user")

    table.accumulate(Event("sessions", {"user": "ada"}))

    assert table.state.entries == {}
    assert table.snapshot() is None


def test_table_accumulate_with_persist__expect_the_row_kept() -> None:
    table = Table(
        "sessions", source="sessions", columns=["user", "ip"], key="user", persist=True
    )

    table.accumulate(Event("sessions", {"user": "ada", "ip": "10.0.0.1"}))

    assert table.state.entries == {"ada": {"user": "ada", "ip": "10.0.0.1"}}
    assert table.snapshot() == table.state.snapshot()


def test_table_accumulate_with_a_missing_key_field__expect_it_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    table = Table(
        "sessions", source="sessions", columns=["user"], key="user", persist=True
    )

    with caplog.at_level(logging.WARNING, logger="dachshund"):
        table.accumulate(Event("sessions", {"ip": "10.0.0.1"}))

    assert table.state.entries == {}
    assert "carries no 'user'" in caplog.text


def test_table_accumulate_with_delete__expect_the_row_dropped() -> None:
    table = Table(
        "sessions", source="sessions", columns=["user"], key="user", persist=True
    )
    table.accumulate(Event("sessions", {"user": "ada"}))

    table.accumulate(Event("sessions", {"user": "ada", "_delete": True}))

    assert table.state.entries == {}


def test_table_accumulate_with_delete_false__expect_the_field_dropped_not_the_row() -> (
    None
):
    table = Table(
        "sessions", source="sessions", columns=["user", "ip"], key="user", persist=True
    )

    table.accumulate(
        Event("sessions", {"user": "ada", "ip": "10.0.0.1", "_delete": False})
    )

    assert table.state.entries == {"ada": {"user": "ada", "ip": "10.0.0.1"}}


def test_table_accumulate_with_an_int_key_after_restore__expect_no_duplicate_row() -> (
    None
):
    table = Table(
        "members", source="members", columns=["id", "name"], key="id", persist=True
    )
    # Simulates state coming back after a restart: JSON round-tripping
    # through Storage stringified the row key.
    table.restore({"entries": {"42": {"id": 42, "name": "ada"}}, "seen_at": {}})

    table.accumulate(Event("members", {"id": 42, "name": "ada (renamed)"}))

    assert table.state.entries == {"42": {"id": 42, "name": "ada (renamed)"}}


def test_table_sweep__expect_untouched_rows_dropped() -> None:
    table = Table(
        "sessions", source="sessions", columns=["user"], key="user", persist=True
    )
    table.accumulate(Event("sessions", {"user": "ada"}, at=_at(1.0)))
    table.accumulate(Event("sessions", {"user": "bob"}, at=_at(5.0)))

    table.sweep(before=3.0)

    assert table.state.entries == {"bob": {"user": "bob"}}


def test_table_restore__expect_the_rows_seeded() -> None:
    table = Table(
        "sessions", source="sessions", columns=["user"], key="user", persist=True
    )

    table.restore({"entries": {"ada": {"user": "ada"}}, "seen_at": {"ada": 1.0}})

    assert table.state.entries == {"ada": {"user": "ada"}}


def test_table_render_with_persist__expect_the_kept_rows_not_the_events() -> None:
    table = Table(
        "sessions", source="sessions", columns=["user"], key="user", persist=True
    )
    table.restore({"entries": {"ada": {"user": "ada"}}, "seen_at": {}})

    # A stale event, ignored: a persisting table reads its own kept rows.
    events = [Event("sessions", {"user": "bob"})]

    assert table.render(events) == {
        "columns": ["user"],
        "rows": [{"fields": {"user": "ada"}}],
    }


@pytest.mark.asyncio
async def test_table_page__expect_the_first_page_and_a_cursor_for_the_next() -> None:
    table = Table("sessions", source="sessions", columns=["user"], key="user")
    events = [Event("sessions", {"user": f"user{i}"}) for i in range(7)]

    first = await table.page(events, None, {})

    assert [row["fields"]["user"] for row in first["rows"]] == [
        f"user{i}" for i in range(5)
    ]
    assert first["next_cursor"] == "user4"
    assert first["page_size"] == 5


@pytest.mark.asyncio
async def test_table_page__expect_the_next_cursor_continuing_correctly() -> None:
    table = Table("sessions", source="sessions", columns=["user"], key="user")
    events = [Event("sessions", {"user": f"user{i}"}) for i in range(7)]

    second = await table.page(events, "user4", {})

    assert [row["fields"]["user"] for row in second["rows"]] == ["user5", "user6"]
    assert second["next_cursor"] is None


@pytest.mark.asyncio
async def test_table_page_with_a_stale_cursor__expect_it_restarted_from_the_beginning() -> (
    None
):
    table = Table("sessions", source="sessions", columns=["user"], key="user")
    events = [Event("sessions", {"user": "ada"})]

    page = await table.page(events, "nope", {})

    assert page["rows"] == [{"fields": {"user": "ada"}}]


@pytest.mark.asyncio
async def test_table_page_without_a_key__expect_positional_cursors() -> None:
    table = Table("sessions", source="sessions", columns=["user"])
    events = [Event("sessions", {"user": f"user{i}"}) for i in range(7)]

    first = await table.page(events, None, {})
    second = await table.page(events, first["next_cursor"], {})

    assert first["next_cursor"] == "4"
    assert [row["fields"]["user"] for row in second["rows"]] == ["user5", "user6"]


@pytest.mark.asyncio
async def test_table_page_of_an_empty_table__expect_an_empty_page() -> None:
    table = Table("sessions", source="sessions", columns=["user"], key="user")

    page = await table.page([], None, {})

    assert page == {
        "columns": ["user"],
        "rows": [],
        "next_cursor": None,
        "page_size": 5,
    }


@pytest.mark.asyncio
async def test_table_page_with_persist__expect_the_kept_rows_paginated() -> None:
    table = Table(
        "sessions", source="sessions", columns=["user"], key="user", persist=True
    )

    for i in range(6):
        table.accumulate(Event("sessions", {"user": f"user{i}"}))

    first = await table.page([], None, {})

    assert len(first["rows"]) == 5
    assert first["next_cursor"] is not None


@pytest.mark.asyncio
async def test_table_page_with_persist_after_the_cursor_row_is_deleted__expect_it_resumed() -> (
    None
):
    table = Table(
        "sessions", source="sessions", columns=["user"], key="user", persist=True
    )
    for i in range(7):
        table.accumulate(Event("sessions", {"user": f"user{i}"}))

    cursor = (await table.page([], None, {}))["next_cursor"]
    table.accumulate(Event("sessions", {"user": "user4", "_delete": True}))

    resumed = await table.page([], cursor, {})

    assert [row["fields"]["user"] for row in resumed["rows"]] == ["user5", "user6"]


@pytest.mark.asyncio
async def test_table_page_with_persist__expect_an_updated_row_not_moving_its_cursor() -> (
    None
):
    table = Table(
        "sessions",
        source="sessions",
        columns=["user", "note"],
        key="user",
        persist=True,
    )
    for i in range(6):
        table.accumulate(Event("sessions", {"user": f"user{i}"}))

    cursor = (await table.page([], None, {}))["next_cursor"]
    table.accumulate(Event("sessions", {"user": "user0", "note": "updated"}))

    resumed = await table.page([], cursor, {})

    assert [row["fields"]["user"] for row in resumed["rows"]] == ["user5"]


@pytest.mark.asyncio
async def test_table_page_with_a_custom_page_size__expect_it_honoured() -> None:
    table = Table(
        "sessions", source="sessions", columns=["user"], key="user", page_size=2
    )
    events = [Event("sessions", {"user": f"user{i}"}) for i in range(3)]

    first = await table.page(events, None, {})

    assert len(first["rows"]) == 2
    assert first["page_size"] == 2


@pytest.mark.asyncio
async def test_table_page_with_a_sync_loader__expect_its_rows_and_cursor() -> None:
    def load(ctx, cursor: str | None, page_size: int) -> tuple[list[dict], str | None]:
        assert ctx == {"db": "session"}
        assert cursor == "a-cursor"
        assert page_size == 5
        return [{"user": "ada", "_guild_id": "1"}], "next-cursor"

    table = Table("sessions", source="sessions", columns=["user"], loader=load)

    page = await table.page([], "a-cursor", {"db": "session"})

    assert page["rows"] == [{"fields": {"user": "ada", "guild_id": "1"}}]
    assert page["next_cursor"] == "next-cursor"


@pytest.mark.asyncio
async def test_table_page_with_an_async_loader__expect_its_rows_and_cursor() -> None:
    async def load(ctx, cursor: str | None, page_size: int) -> tuple[list[dict], str | None]:
        return [{"user": "bob"}], None

    table = Table("sessions", source="sessions", columns=["user"], loader=load)

    page = await table.page([], None, {})

    assert page["rows"] == [{"fields": {"user": "bob"}}]
    assert page["next_cursor"] is None


@pytest.mark.asyncio
async def test_table_page_with_a_loader__expect_host_loop_passed_through() -> None:
    seen_loop = None

    async def load(ctx, cursor: str | None, page_size: int) -> tuple[list[dict], str | None]:
        nonlocal seen_loop
        seen_loop = asyncio.get_running_loop()
        return [], None

    host_loop = asyncio.new_event_loop()
    thread = threading.Thread(target=host_loop.run_forever, daemon=True)
    thread.start()

    table = Table("sessions", source="sessions", columns=["user"], loader=load)

    try:
        await table.page([], None, {}, host_loop)
    finally:
        host_loop.call_soon_threadsafe(host_loop.stop)
        thread.join(5)

    assert seen_loop is host_loop


def test_table_with_loader_and_persist__expect_value_error() -> None:
    def load(ctx, cursor: str | None, page_size: int) -> tuple[list[dict], str | None]:
        return [], None

    with pytest.raises(ValueError, match="either self-contained or fully delegated"):
        Table(
            "sessions",
            source="sessions",
            columns=["user"],
            key="user",
            persist=True,
            loader=load,
        )


def test_table_accumulate_with_a_loader__expect_nothing_kept() -> None:
    def load(ctx, cursor: str | None, page_size: int) -> tuple[list[dict], str | None]:
        return [], None

    table = Table("sessions", source="sessions", columns=["user"], loader=load)

    table.accumulate(Event("sessions", {"user": "ada"}))

    assert table.state.entries == {}
