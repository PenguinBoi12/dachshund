import asyncio
import threading
from collections.abc import Iterator

import pytest
from aiohttp.test_utils import TestClient, TestServer

import dachshund
from dachshund import registry
from dachshund.actions import (
    Action,
    action_card,
    bind_args,
    invoke,
    resolve_row_actions,
    run,
)
from dachshund.registry import Dashboard
from dachshund.runtime.http import create_app


@pytest.fixture(autouse=True)
def no_dashboard_left_behind() -> Iterator[None]:
    yield
    dachshund.shutdown()
    registry._dashboard = None


def test_action__expect_it_registered() -> None:
    dashboard = Dashboard(path=":memory:")

    @dashboard.action("block_user", label="Block")
    def block_user(ctx, user_id: str) -> dict:
        return {"blocked": user_id}

    assert dashboard.actions.keys() == {"block_user"}
    assert dashboard.actions["block_user"].handler is block_user
    assert dashboard.actions["block_user"].label == "Block"


def test_action_with_a_duplicate_name__expect_value_error() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("ping")(lambda ctx: None)

    with pytest.raises(ValueError, match="already exists"):
        dashboard.action("ping")(lambda ctx: None)


def test_action_without_confirm__expect_it_false_by_default() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("ping")(lambda ctx: None)

    assert dashboard.actions["ping"].confirm is False


def test_action_with_confirm_false__expect_it_kept() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("ping", confirm=False)(lambda ctx: None)

    assert dashboard.actions["ping"].confirm is False


def test_action_with_confirm_true__expect_it_kept() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("ping", confirm=True)(lambda ctx: None)

    assert dashboard.actions["ping"].confirm is True


def test_module_level_action__expect_the_default_dashboard() -> None:
    dachshund.default(path=":memory:")

    @dachshund.action("ping")
    def ping(ctx) -> dict:
        return {"pong": True}

    assert dachshund.default().actions["ping"].handler is ping


def test_action_without_a_leading_ctx_param__expect_type_error() -> None:
    dashboard = Dashboard(path=":memory:")

    with pytest.raises(TypeError, match="ctx"):
        dashboard.action("ping")(lambda: None)


def test_action_with_ctx_named_differently__expect_type_error() -> None:
    dashboard = Dashboard(path=":memory:")

    with pytest.raises(TypeError, match="ctx"):
        dashboard.action("ping")(lambda context: None)


def test_action_with_no_params_at_all__expect_type_error() -> None:
    dashboard = Dashboard(path=":memory:")

    def handler() -> None:
        pass

    with pytest.raises(TypeError, match="ctx"):
        dashboard.action("ping")(handler)


def test_action_with_ctx_first__expect_it_registered() -> None:
    dashboard = Dashboard(path=":memory:")

    dashboard.action("ping")(lambda ctx: None)  # no error

    assert "ping" in dashboard.actions


def test_bind_args__expect_extra_keys_dropped() -> None:
    def handler(ctx, user_id: str) -> None:
        pass

    kwargs = bind_args(handler, {"user_id": "42", "issuer": "tomcat"})

    assert kwargs == {"user_id": "42"}


def test_bind_args_missing_a_required_arg__expect_type_error() -> None:
    def handler(ctx, user_id: str) -> None:
        pass

    with pytest.raises(TypeError):
        bind_args(handler, {})


def test_bind_args_excludes_ctx_from_filtering_and_validation() -> None:
    def handler(ctx, user_id: str) -> None:
        pass

    kwargs = bind_args(handler, {"user_id": "42", "ctx": "spoofed"})

    assert kwargs == {"user_id": "42"}


@pytest.mark.asyncio
async def test_run_action_with_a_sync_handler__expect_its_result() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("block_user")(lambda ctx, user_id: {"blocked": user_id})

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.post(
            "/_actions/block_user", json={"args": {"user_id": "42"}}
        )
        body = await response.json()

    assert response.status == 200
    assert body == {"ok": True, "result": {"blocked": "42"}}


@pytest.mark.asyncio
async def test_run_action_with_an_async_handler__expect_its_result() -> None:
    dashboard = Dashboard(path=":memory:")

    async def ping(ctx) -> dict:
        return {"pong": True}

    dashboard.action("ping")(ping)

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.post("/_actions/ping", json={"args": {}})
        body = await response.json()

    assert response.status == 200
    assert body == {"ok": True, "result": {"pong": True}}


@pytest.mark.asyncio
async def test_run_action_with_context__expect_the_real_object() -> None:
    bot = object()
    dashboard = Dashboard(path=":memory:", context={"bot": bot})
    seen = None

    async def handler(ctx) -> dict:
        nonlocal seen
        seen = ctx
        return {"ok": True}

    dashboard.action("use_context")(handler)

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.post(
            "/_actions/use_context", json={"args": {"bot": "fake"}}
        )
        body = await response.json()

    assert response.status == 200
    assert body == {"ok": True, "result": {"ok": True}}
    assert seen["bot"] is bot


@pytest.mark.asyncio
async def test_run_action_without_a_body__expect_empty_args() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("ping")(lambda ctx: {"pong": True})

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.post("/_actions/ping", json={})
        body = await response.json()

    assert response.status == 200
    assert body == {"ok": True, "result": {"pong": True}}


@pytest.mark.asyncio
async def test_run_action_unknown__expect_not_found() -> None:
    dashboard = Dashboard(path=":memory:")

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.post("/_actions/nope", json={"args": {}})
        body = await response.json()

    assert response.status == 404
    assert body["ok"] is False


@pytest.mark.asyncio
async def test_run_action_with_a_missing_required_arg__expect_bad_request() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("block_user")(lambda ctx, user_id: {"blocked": user_id})

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.post("/_actions/block_user", json={"args": {}})
        body = await response.json()

    assert response.status == 400
    assert body["ok"] is False


@pytest.mark.asyncio
async def test_run_action_with_malformed_json__expect_bad_request() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("ping")(lambda ctx: None)

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.post(
            "/_actions/ping", data="not json", headers={"Content-Type": "application/json"}
        )
        body = await response.json()

    assert response.status == 400
    assert body["ok"] is False


@pytest.mark.asyncio
async def test_run_action_that_raises__expect_server_error_with_message() -> None:
    dashboard = Dashboard(path=":memory:")

    def boom(ctx) -> None:
        raise RuntimeError("kaboom")

    dashboard.action("boom")(boom)

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.post("/_actions/boom", json={"args": {}})
        body = await response.json()

    assert response.status == 500
    assert body == {"ok": False, "error": "kaboom"}


@pytest.mark.asyncio
async def test_run_action_that_raises_type_error__expect_server_error_not_bad_request() -> (
    None
):
    dashboard = Dashboard(path=":memory:")

    def boom(ctx, **kwargs: object) -> None:
        raise TypeError("kaboom")

    dashboard.action("boom")(boom)

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.post("/_actions/boom", json={"args": {}})
        body = await response.json()

    assert response.status == 500
    assert body == {"ok": False, "error": "kaboom"}


@pytest.mark.asyncio
async def test_run_a_sync_function__expect_it_run_off_the_loop() -> None:
    def handler(x: int) -> int:
        return x + 1

    assert await run(handler, 1) == 2


@pytest.mark.asyncio
async def test_run_an_async_function_without_a_host_loop__expect_the_current_loop() -> (
    None
):
    async def handler(x: int) -> int:
        return x + 1

    assert await run(handler, 1) == 2


@pytest.mark.asyncio
async def test_run_with_a_host_loop__expect_the_coroutine_run_there() -> None:
    host_loop = asyncio.new_event_loop()
    thread = threading.Thread(target=host_loop.run_forever, daemon=True)
    thread.start()

    seen_loop = None

    async def handler() -> str:
        nonlocal seen_loop
        seen_loop = asyncio.get_running_loop()
        return "ok"

    try:
        result = await run(handler, host_loop=host_loop)
    finally:
        host_loop.call_soon_threadsafe(host_loop.stop)
        thread.join(5)

    assert result == "ok"
    assert seen_loop is host_loop
    assert seen_loop is not asyncio.get_running_loop()


@pytest.mark.asyncio
async def test_run__expect_args_and_kwargs_passed_through() -> None:
    def handler(a: int, b: int = 0) -> int:
        return a + b

    assert await run(handler, 1, b=2) == 3


@pytest.mark.asyncio
async def test_invoke_with_a_host_loop__expect_the_handler_run_there() -> None:
    host_loop = asyncio.new_event_loop()
    thread = threading.Thread(target=host_loop.run_forever, daemon=True)
    thread.start()

    seen_loop = None

    async def handler(ctx) -> str:
        nonlocal seen_loop
        seen_loop = asyncio.get_running_loop()
        return "ok"

    try:
        result = await invoke(Action("test", handler), {}, {}, host_loop)
    finally:
        host_loop.call_soon_threadsafe(host_loop.stop)
        thread.join(5)

    assert result == "ok"
    assert seen_loop is host_loop
    assert seen_loop is not asyncio.get_running_loop()


@pytest.mark.asyncio
async def test_invoke_without_a_host_loop__expect_the_current_loop() -> None:
    async def handler(ctx) -> str:
        return "ok"

    result = await invoke(Action("test", handler), {}, {})

    assert result == "ok"


@pytest.mark.asyncio
async def test_invoke_passes_context_to_a_sync_handler() -> None:
    seen = None

    def handler(ctx) -> None:
        nonlocal seen
        seen = ctx

    await invoke(Action("test", handler), {}, {"bot": "b"})

    assert seen == {"bot": "b"}


@pytest.mark.asyncio
async def test_invoke_passes_context_to_an_async_handler() -> None:
    seen = None

    async def handler(ctx) -> None:
        nonlocal seen
        seen = ctx

    await invoke(Action("test", handler), {}, {"bot": "b"})

    assert seen == {"bot": "b"}


@pytest.mark.asyncio
async def test_dashboard_start_from_a_running_loop__expect_it_captured_as_host_loop() -> (
    None
):
    dashboard = Dashboard(path=":memory:", port=0)
    dashboard.start()

    try:
        assert dashboard.host_loop is asyncio.get_running_loop()
    finally:
        dashboard.stop()


def test_dashboard_start_without_a_running_loop__expect_no_host_loop() -> None:
    dashboard = Dashboard(path=":memory:", port=0)
    dashboard.start()

    try:
        assert dashboard.host_loop is None
    finally:
        dashboard.stop()


def test_dashboard_with_context__expect_it_kept() -> None:
    sentinel = object()
    assert Dashboard(path=":memory:", context={"bot": sentinel}).context == {
        "bot": sentinel
    }


def test_dashboard_without_context__expect_an_empty_dict() -> None:
    assert Dashboard(path=":memory:").context == {}


def test_action_card_without_args__expect_an_empty_dict() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("ping")(lambda ctx: None)

    assert action_card(dashboard.actions, "ping")["args"] == {}


def test_action_card_with_args__expect_them_carried() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("block_user")(lambda ctx, user_id: None)

    card = action_card(dashboard.actions, "block_user", {"user_id": "42"})

    assert card["args"] == {"user_id": "42"}


def test_action_card_unregistered__expect_a_sensible_fallback() -> None:
    card = action_card({}, "nope")

    assert card == {"name": "nope", "label": "nope", "confirm": False, "args": {}}


def test_resolve_row_actions_on_a_widget_that_doesnt_render_its_own__expect_no_change() -> (
    None
):
    dashboard = Dashboard(path=":memory:")
    payload = {"rows": [{"fields": {"user": "ada"}}]}

    dashboard.widget("cpu", type="number", actions=["ping"])
    resolve_row_actions(dashboard.actions, dashboard.widgets["cpu"], payload)

    assert "actions" not in payload["rows"][0]


def test_resolve_row_actions_on_a_table__expect_every_row_carrying_them() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("ban", label="Ban", confirm=True)(lambda ctx, user: None)
    dashboard.widget("sessions", type="table", columns=["user"], actions=["ban"])
    payload = {
        "columns": ["user"],
        "rows": [{"fields": {"user": "ada"}}, {"fields": {"user": "bob"}}],
    }

    resolve_row_actions(dashboard.actions, dashboard.widgets["sessions"], payload)

    expected = [{"name": "ban", "label": "Ban", "confirm": True, "args": {}}]
    assert payload["rows"][0]["actions"] == expected
    assert payload["rows"][1]["actions"] == expected


def test_resolve_row_actions_with_action_args__expect_them_on_every_row() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("ban", label="Ban", confirm=True)(lambda ctx, name, guild_id: None)
    dashboard.widget(
        "members",
        type="table",
        columns=["id", "name"],
        actions=["ban"],
        action_args={"ban": {"guild_id": 1349086642446532639}},
    )
    payload = {
        "columns": ["id", "name"],
        "rows": [{"fields": {"id": "1", "name": "ada"}}],
    }

    resolve_row_actions(dashboard.actions, dashboard.widgets["members"], payload)

    assert payload["rows"][0]["actions"] == [
        {
            "name": "ban",
            "label": "Ban",
            "confirm": True,
            "args": {"guild_id": 1349086642446532639},
        }
    ]
