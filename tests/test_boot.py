import os
import socket
from collections.abc import Iterator
from urllib.request import urlopen

import pytest
from aiohttp import web

from dachshund.runtime.boot import Runtime
from dachshund.runtime.http import create_app


def build_app() -> web.Application:
    return create_app(name="Ada")


@pytest.fixture
def runtime() -> Iterator[Runtime]:
    runtime = Runtime(build_app, port=0)
    yield runtime
    runtime.stop()


@pytest.fixture
def taken_port() -> Iterator[int]:
    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        bound.listen()
        yield bound.getsockname()[1]


def test_start__expect_dashboard_served(runtime: Runtime) -> None:
    runtime.start()

    with urlopen(runtime.url) as response:
        assert response.status == 200


def test_start_with_port_zero__expect_bound_port_resolved(runtime: Runtime) -> None:
    runtime.start()

    assert runtime.is_running
    assert runtime.port > 0
    assert runtime.url == f"http://127.0.0.1:{runtime.port}"


def test_start_when_already_running__expect_same_port(runtime: Runtime) -> None:
    runtime.start()
    port = runtime.port
    runtime.start()

    assert runtime.port == port


def test_start_with_a_taken_port__expect_os_error(taken_port: int) -> None:
    runtime = Runtime(build_app, port=taken_port)

    with pytest.raises(OSError):
        runtime.start()

    assert not runtime.is_running


def test_start_when_serving_fails__expect_the_error_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def explode(self: Runtime) -> None:
        raise ValueError("boom")

    monkeypatch.setattr(Runtime, "_serve", explode)
    runtime = Runtime(build_app, port=0)

    with pytest.raises(ValueError, match="boom"):
        runtime.start()

    assert not runtime.is_running


def test_start_after_stop__expect_dashboard_served_again(runtime: Runtime) -> None:
    runtime.start()
    runtime.stop()
    runtime.start()

    assert runtime.is_running

    with urlopen(runtime.url) as response:
        assert response.status == 200


def test_stop__expect_runtime_stopped(runtime: Runtime) -> None:
    runtime.start()
    runtime.stop()

    assert not runtime.is_running

    with pytest.raises(RuntimeError):
        runtime.port


def test_stop_when_not_running__expect_no_error(runtime: Runtime) -> None:
    runtime.stop()

    assert not runtime.is_running


@pytest.mark.filterwarnings("ignore:This process:DeprecationWarning")
def test_is_running_in_a_forked_child__expect_false(runtime: Runtime) -> None:
    runtime.start()

    child = os.fork()

    if child == 0:
        os._exit(0 if not runtime.is_running else 1)

    _, status = os.waitpid(child, 0)

    assert os.waitstatus_to_exitcode(status) == 0
    assert runtime.is_running
