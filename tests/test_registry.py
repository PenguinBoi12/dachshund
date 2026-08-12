import logging
import threading
from collections.abc import Iterator
from typing import Any, Callable
from urllib.request import urlopen

import pytest

import dachshund
from dachshund import registry
from dachshund.registry import Dashboard


@pytest.fixture(autouse=True)
def no_dashboard_left_running() -> Iterator[None]:
    yield
    dachshund.shutdown()


def test_dashboard_start__expect_the_dashboard_served() -> None:
    dashboard = Dashboard("Ada", description="Code Society's Matrix bot", port=0)
    dashboard.start()

    try:
        assert dashboard.is_running
        assert dashboard.name == "Ada"
        assert dashboard.description == "Code Society's Matrix bot"

        with urlopen(dashboard.url) as response:
            assert response.status == 200
    finally:
        dashboard.stop()

    assert not dashboard.is_running


def test_init_when_already_running__expect_the_same_dashboard() -> None:
    dashboard = dachshund.init("Ada", port=0)

    assert dachshund.init("Ada", port=0) is dashboard
    assert dashboard.is_running

    dachshund.shutdown()

    assert not dashboard.is_running


def test_init_with_a_name_and_description__expect_them_kept() -> None:
    dashboard = dachshund.init("Ada", description="Code Society's Matrix bot", port=0)

    assert dashboard.name == "Ada"
    assert dashboard.description == "Code Society's Matrix bot"


def test_init_with_another_address__expect_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    dashboard = dachshund.init("Ada", port=0)

    with caplog.at_level(logging.WARNING, logger="dachshund"):
        assert dachshund.init("Ada", port=9999) is dashboard

    assert "already running" in caplog.text
    assert dashboard.runtime.requested_port == 0


def test_init_from_concurrent_callers__expect_a_single_dashboard() -> None:
    dashboards: list[Dashboard] = []
    start = threading.Barrier(4)

    def racer() -> None:
        start.wait()
        dashboards.append(dachshund.init("Ada", port=0))

    threads = [threading.Thread(target=racer) for _ in range(4)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)

    assert len(dashboards) == 4
    assert len({id(dashboard) for dashboard in dashboards}) == 1


def test_init_after_a_manual_stop__expect_a_single_exit_hook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hooks: list[Callable[..., Any]] = []

    monkeypatch.setattr(registry.atexit, "register", hooks.append)
    monkeypatch.setattr(registry.atexit, "unregister", hooks.remove)

    dachshund.init("Ada", port=0).stop()
    dachshund.init("Ada", port=0)

    assert len(hooks) == 1


def test_shutdown_without_a_dashboard__expect_no_error() -> None:
    dachshund.shutdown()


def test_init_without_a_name__expect_a_dashboard_anyway() -> None:
    dashboard = dachshund.init(port=0)

    assert dashboard.is_running
    assert dashboard.name is None


@pytest.mark.parametrize("name", ["", "   "])
def test_dashboard_with_a_blank_name__expect_value_error(name: str) -> None:
    with pytest.raises(ValueError, match="cannot be blank"):
        Dashboard(name)
