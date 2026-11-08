import asyncio
import logging
import threading
from datetime import datetime, timezone

import pytest

from dachshund.storage import Event
from dachshund.widgets.query import TableQuery
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


def _users(*names: str) -> list[Event]:
    return [Event("sessions", {"user": name}) for name in names]


def _names(page: dict) -> list:
    return [row["fields"].get("user") for row in page["rows"]]


@pytest.mark.asyncio
async def test_table_page__expect_the_first_page_and_a_total() -> None:
    table = Table("sessions", source="sessions", columns=["user"], key="user")
    events = _users(*(f"user{i}" for i in range(12)))

    page = await table.page(events, TableQuery(), {})

    assert _names(page) == [f"user{i}" for i in range(10)]
    assert (page["total"], page["offset"], page["limit"]) == (12, 0, 10)


@pytest.mark.asyncio
async def test_table_page_with_an_offset__expect_the_rows_after_it() -> None:
    table = Table("sessions", source="sessions", columns=["user"], key="user")
    events = _users(*(f"user{i}" for i in range(12)))

    page = await table.page(events, TableQuery(offset=10), {})

    assert _names(page) == ["user10", "user11"]


@pytest.mark.asyncio
async def test_table_page_with_a_custom_page_size__expect_it_as_the_limit() -> None:
    table = Table(
        "sessions", source="sessions", columns=["user"], key="user", page_size=2
    )

    page = await table.page(_users("a", "b", "c"), TableQuery(), {})

    assert (len(page["rows"]), page["limit"]) == (2, 2)


@pytest.mark.asyncio
async def test_table_page_with_a_limit__expect_it_over_the_page_size() -> None:
    table = Table("sessions", source="sessions", columns=["user"], key="user")

    page = await table.page(_users("a", "b", "c"), TableQuery(limit=1), {})

    assert _names(page) == ["a"]


@pytest.mark.asyncio
async def test_table_page_of_an_empty_table__expect_an_empty_page() -> None:
    table = Table("sessions", source="sessions", columns=["user"], key="user")

    page = await table.page([], TableQuery(), {})

    assert page == {
        "columns": ["user"],
        "rows": [],
        "total": 0,
        "offset": 0,
        "limit": 10,
        "sortable": ["user"],
        "search": True,
        "sort_by": None,
        "descending": False,
    }


@pytest.mark.asyncio
async def test_table_page_with_a_search__expect_matching_rows_case_insensitively() -> (
    None
):
    table = Table("sessions", source="sessions", columns=["user", "ip"], key="user")
    events = [
        Event("sessions", {"user": "Ada", "ip": "10.0.0.1"}),
        Event("sessions", {"user": "bob", "ip": "10.0.0.2"}),
        Event("sessions", {"user": "carol", "ip": "192.168.0.1"}),
    ]

    by_name = await table.page(events, TableQuery(search="ada"), {})
    by_ip = await table.page(events, TableQuery(search="10.0"), {})

    assert (_names(by_name), by_name["total"]) == (["Ada"], 1)
    assert _names(by_ip) == ["Ada", "bob"]


@pytest.mark.asyncio
async def test_table_page_with_a_search__expect_hidden_fields_ignored() -> None:
    table = Table("sessions", source="sessions", columns=["user", "_team"], key="user")
    events = [Event("sessions", {"user": "ada", "_team": "secret"})]

    page = await table.page(events, TableQuery(search="secret"), {})

    assert page["rows"] == []


@pytest.mark.asyncio
async def test_table_page_sorted__expect_ascending_then_descending() -> None:
    table = Table("sessions", source="sessions", columns=["user"], key="user")
    events = _users("carol", "Ada", "bob")

    ascending = await table.page(events, TableQuery(sort_by="user"), {})
    descending = await table.page(
        events, TableQuery(sort_by="user", descending=True), {}
    )

    assert _names(ascending) == ["Ada", "bob", "carol"]
    assert _names(descending) == ["carol", "bob", "Ada"]


@pytest.mark.asyncio
async def test_table_page_sorted__expect_numbers_in_order_and_missing_last() -> None:
    table = Table("scores", source="scores", columns=["user", "score"], key="user")
    events = [
        Event("scores", {"user": "a", "score": 10}),
        Event("scores", {"user": "b"}),
        Event("scores", {"user": "c", "score": 9}),
    ]

    ascending = await table.page(events, TableQuery(sort_by="score"), {})
    descending = await table.page(
        events, TableQuery(sort_by="score", descending=True), {}
    )

    assert _names(ascending) == ["c", "a", "b"]
    assert _names(descending) == ["a", "c", "b"]


@pytest.mark.asyncio
async def test_table_page_sorted_by_an_unsortable_column__expect_it_unsorted() -> None:
    table = Table(
        "sessions",
        source="sessions",
        columns=["user", "ip"],
        key="user",
        sortable=["ip"],
    )

    page = await table.page(_users("b", "a"), TableQuery(sort_by="user"), {})

    assert _names(page) == ["b", "a"]
    assert page["sortable"] == ["ip"]


def test_table_sortable_naming_an_unknown_column__expect_value_error() -> None:
    with pytest.raises(ValueError, match="doesn't show: email"):
        Table("sessions", source="sessions", columns=["user"], sortable=["email"])


@pytest.mark.asyncio
async def test_table_page_with_persist__expect_the_kept_rows_searched_and_sorted() -> (
    None
):
    table = Table(
        "sessions", source="sessions", columns=["user"], key="user", persist=True
    )

    for name in ["carol", "ada", "bob", "adam"]:
        table.accumulate(Event("sessions", {"user": name}))

    page = await table.page([], TableQuery(search="ad", sort_by="user"), {})

    assert (_names(page), page["total"]) == (["ada", "adam"], 2)


@pytest.mark.asyncio
async def test_table_page_with_a_sync_loader__expect_the_query_and_its_rows() -> None:
    def load(ctx, query: TableQuery) -> tuple[list[dict], int | None]:
        assert ctx == {"db": "session"}
        assert query == TableQuery(search="ada", sort_by="user", offset=10, limit=10)
        return [{"user": "ada", "_guild_id": "1"}], 41

    table = Table("sessions", source="sessions", columns=["user"], loader=load)

    page = await table.page(
        [], TableQuery(search="ada", sort_by="user", offset=10), {"db": "session"}
    )

    assert page["rows"] == [{"fields": {"user": "ada", "guild_id": "1"}}]
    assert page["total"] == 41


@pytest.mark.asyncio
async def test_table_page_with_an_async_loader__expect_an_unknown_total_kept() -> None:
    async def load(ctx, query: TableQuery) -> tuple[list[dict], int | None]:
        return [{"user": "bob"}], None

    table = Table("sessions", source="sessions", columns=["user"], loader=load)

    page = await table.page([], TableQuery(), {})

    assert _names(page) == ["bob"]
    assert page["total"] is None


@pytest.mark.asyncio
async def test_table_page_with_a_loader__expect_host_loop_passed_through() -> None:
    seen_loop = None

    async def load(ctx, query: TableQuery) -> tuple[list[dict], int | None]:
        nonlocal seen_loop
        seen_loop = asyncio.get_running_loop()
        return [], None

    host_loop = asyncio.new_event_loop()
    thread = threading.Thread(target=host_loop.run_forever, daemon=True)
    thread.start()

    table = Table("sessions", source="sessions", columns=["user"], loader=load)

    try:
        await table.page([], TableQuery(), {}, host_loop)
    finally:
        host_loop.call_soon_threadsafe(host_loop.stop)
        thread.join(5)

    assert seen_loop is host_loop


def test_table_with_loader_and_persist__expect_value_error() -> None:
    def load(ctx, query: TableQuery) -> tuple[list[dict], int | None]:
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
    def load(ctx, query: TableQuery) -> tuple[list[dict], int | None]:
        return [], None

    table = Table("sessions", source="sessions", columns=["user"], loader=load)

    table.accumulate(Event("sessions", {"user": "ada"}))

    assert table.state.entries == {}
