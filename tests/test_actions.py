import asyncio
import threading
from collections.abc import Iterator

import pytest
from aiohttp.test_utils import TestClient, TestServer

import dachshund
from dachshund import registry
from dachshund.actions import Action, bind_args, invoke
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
    def block_user(user_id: str) -> dict:
        return {"blocked": user_id}

    assert dashboard.actions.keys() == {"block_user"}
    assert dashboard.actions["block_user"].handler is block_user
    assert dashboard.actions["block_user"].label == "Block"


def test_action_with_a_duplicate_name__expect_value_error() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("ping")(lambda: None)

    with pytest.raises(ValueError, match="already exists"):
        dashboard.action("ping")(lambda: None)


def test_action_without_confirm__expect_it_false_by_default() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("ping")(lambda: None)

    assert dashboard.actions["ping"].confirm is False


def test_action_with_confirm_false__expect_it_kept() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("ping", confirm=False)(lambda: None)

    assert dashboard.actions["ping"].confirm is False


def test_action_with_confirm_true__expect_it_kept() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("ping", confirm=True)(lambda: None)

    assert dashboard.actions["ping"].confirm is True


def test_module_level_action__expect_the_default_dashboard() -> None:
    dachshund.default(path=":memory:")

    @dachshund.action("ping")
    def ping() -> dict:
        return {"pong": True}

    assert dachshund.default().actions["ping"].handler is ping


def test_bind_args__expect_extra_keys_dropped() -> None:
    def handler(user_id: str) -> None:
        pass

    kwargs = bind_args(handler, {"user_id": "42", "issuer": "tomcat"})

    assert kwargs == {"user_id": "42"}


def test_bind_args_missing_a_required_arg__expect_type_error() -> None:
    def handler(user_id: str) -> None:
        pass

    with pytest.raises(TypeError):
        bind_args(handler, {})


@pytest.mark.asyncio
async def test_run_action_with_a_sync_handler__expect_its_result() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("block_user")(lambda user_id: {"blocked": user_id})

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

    async def ping() -> dict:
        return {"pong": True}

    dashboard.action("ping")(ping)

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.post("/_actions/ping", json={"args": {}})
        body = await response.json()

    assert response.status == 200
    assert body == {"ok": True, "result": {"pong": True}}


@pytest.mark.asyncio
async def test_run_action_without_a_body__expect_empty_args() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("ping")(lambda: {"pong": True})

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
    dashboard.action("block_user")(lambda user_id: {"blocked": user_id})

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.post("/_actions/block_user", json={"args": {}})
        body = await response.json()

    assert response.status == 400
    assert body["ok"] is False


@pytest.mark.asyncio
async def test_run_action_with_malformed_json__expect_bad_request() -> None:
    dashboard = Dashboard(path=":memory:")
    dashboard.action("ping")(lambda: None)

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

    def boom() -> None:
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

    def boom(**kwargs: object) -> None:
        raise TypeError("kaboom")

    dashboard.action("boom")(boom)

    async with TestClient(TestServer(create_app(dashboard))) as client:
        response = await client.post("/_actions/boom", json={"args": {}})
        body = await response.json()

    assert response.status == 500
    assert body == {"ok": False, "error": "kaboom"}


@pytest.mark.asyncio
async def test_invoke_with_a_host_loop__expect_the_handler_run_there() -> None:
    host_loop = asyncio.new_event_loop()
    thread = threading.Thread(target=host_loop.run_forever, daemon=True)
    thread.start()

    seen_loop = None

    async def handler() -> str:
        nonlocal seen_loop
        seen_loop = asyncio.get_running_loop()
        return "ok"

    try:
        result = await invoke(Action("test", handler), {}, host_loop)
    finally:
        host_loop.call_soon_threadsafe(host_loop.stop)
        thread.join(5)

    assert result == "ok"
    assert seen_loop is host_loop
    assert seen_loop is not asyncio.get_running_loop()


@pytest.mark.asyncio
async def test_invoke_without_a_host_loop__expect_the_current_loop() -> None:
    async def handler() -> str:
        return "ok"

    result = await invoke(Action("test", handler), {})

    assert result == "ok"


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
