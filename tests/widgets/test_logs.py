import logging
import threading
from collections.abc import Iterator
from typing import Any

import pytest

from dachshund.registry import Dashboard
from dachshund.runtime.boot import RUNTIME_THREAD
from dachshund.storage.events import Event
from dachshund.widgets import Logs
from dachshund.widgets.query import TableQuery


@pytest.fixture
def dashboard() -> Iterator[Dashboard]:
    dashboard = Dashboard(path=":memory:")
    yield dashboard

    for widget in list(dashboard.widgets.values()):
        widget.unbind()


@pytest.fixture(autouse=True)
def debug_loggers() -> Iterator[None]:
    root = logging.getLogger()
    level = root.level
    root.setLevel(logging.DEBUG)
    yield
    root.setLevel(level)


def add(dashboard: Dashboard, widget: Logs) -> Logs:
    with dashboard.row():
        dashboard.add(widget)
    return widget


def lines(dashboard: Dashboard) -> list[dict[str, Any]]:
    return [event.payload for event in dashboard.queue.drain()]


def test_logs_record__expect_an_event_of_its_source(dashboard: Dashboard) -> None:
    add(dashboard, Logs("logs", logger="tests.app"))

    logging.getLogger("tests.app").info("hello %s", "ada")

    [line] = lines(dashboard)
    assert line["message"] == "hello ada"
    assert (line["level"], line["levelno"], line["logger"]) == ("INFO", 20, "tests.app")
    assert line["_exception"] is None


def test_logs_record_with_an_exception__expect_its_traceback(
    dashboard: Dashboard,
) -> None:
    add(dashboard, Logs("logs", logger="tests.app"))

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        logging.getLogger("tests.app").exception("failed")

    [line] = lines(dashboard)
    assert "RuntimeError: boom" in line["_exception"]


def test_logs_of_a_logger__expect_children_captured_and_siblings_not(
    dashboard: Dashboard,
) -> None:
    add(dashboard, Logs("logs", logger="tests.api"))

    logging.getLogger("tests.api.users").warning("child")
    logging.getLogger("tests.web").warning("sibling")

    assert [line["message"] for line in lines(dashboard)] == ["child"]


def test_logs_below_its_level__expect_them_skipped(dashboard: Dashboard) -> None:
    add(dashboard, Logs("logs", logger="tests.app", level="ERROR"))

    logging.getLogger("tests.app").warning("quiet")
    logging.getLogger("tests.app").error("loud")

    assert [line["message"] for line in lines(dashboard)] == ["loud"]


def test_logs_from_the_runtime_thread__expect_them_dropped(
    dashboard: Dashboard,
) -> None:
    add(dashboard, Logs("logs", logger="tests.app"))

    thread = threading.Thread(
        target=lambda: logging.getLogger("tests.app").error("inside"),
        name=RUNTIME_THREAD,
    )
    thread.start()
    thread.join()

    assert lines(dashboard) == []


def test_logs_bind_twice__expect_one_handler_and_unbind_detaches(
    dashboard: Dashboard,
) -> None:
    widget = add(dashboard, Logs("logs", logger="tests.app"))
    captured = logging.getLogger("tests.app")

    widget.bind(dashboard)
    handlers = [handler for handler in captured.handlers if handler is widget.handler]
    widget.unbind()

    assert len(handlers) == 1
    assert widget.handler is None
    assert not any(isinstance(h, type(handlers[0])) for h in captured.handlers)


def test_logs_on_a_quieter_logger__expect_a_warning(
    dashboard: Dashboard, caplog: pytest.LogCaptureFixture
) -> None:
    logging.getLogger("tests.quiet").setLevel(logging.ERROR)

    with caplog.at_level(logging.WARNING, logger="dachshund"):
        add(dashboard, Logs("logs", logger="tests.quiet"))

    logging.getLogger("tests.quiet").setLevel(logging.NOTSET)
    assert "only passes ERROR and up" in caplog.text


def events(*levels: tuple[str, int]) -> list[Event]:
    return [
        Event(
            "logs", {"time": index, "level": name, "levelno": number, "message": name}
        )
        for index, (name, number) in enumerate(levels)
    ]


@pytest.mark.asyncio
async def test_logs_page__expect_newest_first_every_level_by_default() -> None:
    widget = Logs("logs", level="WARNING")
    kept = events(("WARNING", 30), ("ERROR", 40), ("CRITICAL", 50))

    page = await widget.page(kept, TableQuery(), {})

    assert _messages(page) == ["CRITICAL", "ERROR", "WARNING"]
    assert (page["levels"], page["shown"]) == ([30, 40, 50], [])
    assert page["columns"] == ["time", "level", "logger", "message"]


@pytest.mark.asyncio
async def test_logs_page_with_levels__expect_only_those_levels() -> None:
    widget = Logs("logs", level="DEBUG")
    kept = events(
        ("DEBUG", 10), ("INFO", 20), ("WARNING", 30), ("ERROR", 40), ("CRITICAL", 50)
    )

    errors = await widget.page(kept, TableQuery(levels=frozenset({40})), {})
    mixed = await widget.page(kept, TableQuery(levels=frozenset({30, 50})), {})

    assert _messages(errors) == ["ERROR"]
    assert _messages(mixed) == ["CRITICAL", "WARNING"]
    assert mixed["shown"] == [30, 50]


@pytest.mark.asyncio
async def test_logs_page_levels__expect_only_the_captured_ones() -> None:
    page = await Logs("logs").page([], TableQuery(), {})

    assert page["levels"] == [20, 30, 40, 50]


def _messages(page: dict[str, Any]) -> list[str]:
    return [row["fields"]["message"] for row in page["rows"]]


@pytest.mark.parametrize(
    "options, message",
    [
        ({"level": "LOUD"}, "level='LOUD'"),
        ({"persist": True}, "give it `keep`"),
        ({"keep": 0}, "keep at least 1"),
    ],
)
def test_logs_with_bad_options__expect_value_error(
    options: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        Logs("logs", **options)


def test_logs_raw_events__expect_its_keep() -> None:
    assert Logs("logs", keep=42).raw_events() == 42
