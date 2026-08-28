import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dachshund.storage.events import Event
from dachshund.widgets.base import WIDGETS, Widget, build
from dachshund.widgets.button.button import Button
from dachshund.widgets.chart.bar import BarChart
from dachshund.widgets.chart.line import LineChart
from dachshund.widgets.chart.timeseries import TimeSeriesChart
from dachshund.widgets.number.number import Number
from dachshund.widgets.state import KeyedWidget
from dachshund.widgets.table.table import Table

FIXTURE_SCRIPT = Path(__file__).parent / "fixtures" / "gauge.js"


@pytest.mark.parametrize("size", [0, 4])
def test_widget_with_a_size_off_the_grid__expect_value_error(size: int) -> None:
    with pytest.raises(ValueError, match="1 to 3 columns"):
        Widget("latency", source="latency", size=size)


def test_widget_snapshot_by_default__expect_none() -> None:
    assert Widget("latency", source="latency").snapshot() is None


def test_widget_default__expect_rollup_unsafe() -> None:
    assert Widget.rollup_safe is False


def test_line_and_timeseries__expect_rollup_safe() -> None:
    assert LineChart.rollup_safe is True
    assert TimeSeriesChart.rollup_safe is True


def test_table_and_bar__expect_rollup_unsafe() -> None:
    assert Table.rollup_safe is False
    assert BarChart.rollup_safe is False


def test_keyed_widget__expect_table_and_bar_share_it() -> None:
    assert issubclass(Table, KeyedWidget)
    assert issubclass(BarChart, KeyedWidget)


def test_builtin_chart_types__expect_them_registered() -> None:
    assert WIDGETS["bar"] is BarChart
    assert WIDGETS["line"] is LineChart
    assert WIDGETS["timeseries"] is TimeSeriesChart
    assert WIDGETS["number"] is Number
    assert WIDGETS["button"] is Button
    assert WIDGETS["table"] is Table


def test_a_widget_subclass__expect_it_registered_under_its_type() -> None:
    class Gauge(Widget):
        type = "custom_test_gauge"

    assert WIDGETS["custom_test_gauge"] is Gauge


def test_build_of_a_custom_type__expect_it_constructed() -> None:
    class Meter(Widget):
        type = "custom_test_meter"

    widget = build("dial", type="custom_test_meter")

    assert isinstance(widget, Meter)
    assert widget.source == "dial"


def test_widget_script_and_style_default__expect_none() -> None:
    assert Widget.script is None
    assert Widget.style is None


def test_a_widget_with_a_missing_script__expect_a_clear_error() -> None:
    with pytest.raises(FileNotFoundError, match="nope.js"):

        class BadGauge(Widget):
            type = "custom_test_bad_gauge"
            script = Path(__file__).parent / "nope.js"


def test_a_widget_with_a_script__expect_it_registered() -> None:
    class Gauge(Widget):
        type = "custom_test_gauge_with_script"
        script = FIXTURE_SCRIPT

    assert WIDGETS["custom_test_gauge_with_script"].script == FIXTURE_SCRIPT


def test_builtin_charts__expect_them_sharing_one_script_and_style() -> None:
    # The three chart types are one cohesive rendering module, not three.
    assert LineChart.script == BarChart.script == TimeSeriesChart.script
    assert LineChart.style == BarChart.style == TimeSeriesChart.style
    assert LineChart.script is not None and LineChart.script.is_file()
    assert LineChart.style is not None and LineChart.style.is_file()


def test_a_line_without_an_x__expect_type_error() -> None:
    with pytest.raises(TypeError, match="x"):
        LineChart("perf", source="perf")  # type: ignore[call-arg]


def test_a_timeseries_without_an_x__expect_no_error() -> None:
    assert TimeSeriesChart("latency", source="latency").x == ""


def test_a_chart_without_a_y_field__expect_value_error() -> None:
    with pytest.raises(ValueError, match="at least one y field"):
        TimeSeriesChart("perf", source="perf", y=[])


def test_series__expect_a_tuple_however_y_was_given() -> None:
    assert TimeSeriesChart("a", source="a").series == ("value",)
    assert TimeSeriesChart("b", source="b", y="ms").series == ("ms",)
    assert TimeSeriesChart("c", source="c", y=["p50", "p95"]).series == ("p50", "p95")


def test_type_and_op__expect_each_chart_to_declare_its_own() -> None:
    assert (TimeSeriesChart.type, TimeSeriesChart.op) == ("timeseries", "append")
    assert (LineChart.type, LineChart.op) == ("line", "append")
    assert (BarChart.type, BarChart.op) == ("bar", "replace")


def test_timeseries_render__expect_the_columns_uplot_draws() -> None:
    chart = TimeSeriesChart("latency", source="latency")
    now = datetime.now(tz=timezone.utc)
    events = [
        Event("latency", {"value": 96}, at=now - timedelta(seconds=1)),
        Event("latency", {"value": 108}, at=now),
    ]

    assert chart.render(events) == {
        "series": ["value"],
        "x": [(now - timedelta(seconds=1)).timestamp(), now.timestamp()],
        "y": [[96.0, 108.0]],
    }


def test_timeseries_update__expect_a_row_placed_in_time() -> None:
    chart = TimeSeriesChart("latency", source="latency")
    now = datetime.now(tz=timezone.utc)

    assert chart.update(Event("latency", {"value": 96}, at=now)) == {
        "x": now.timestamp(),
        "y": [96.0],
    }


def test_render_with_several_y_fields__expect_a_line_each() -> None:
    chart = TimeSeriesChart("perf", source="perf", y=["p50", "p95"])
    now = datetime.now(tz=timezone.utc)
    events = [
        Event("perf", {"p50": 10, "p95": 40}, at=now - timedelta(seconds=1)),
        Event("perf", {"p50": 12, "p95": 44}, at=now),
    ]

    assert chart.render(events) == {
        "series": ["p50", "p95"],
        "x": [(now - timedelta(seconds=1)).timestamp(), now.timestamp()],
        "y": [[10.0, 12.0], [40.0, 44.0]],
    }


def test_update_with_several_y_fields__expect_one_row() -> None:
    chart = TimeSeriesChart("perf", source="perf", y=["p50", "p95"])
    now = datetime.now(tz=timezone.utc)

    assert chart.update(Event("perf", {"p50": 10, "p95": 40}, at=now)) == {
        "x": now.timestamp(),
        "y": [10.0, 40.0],
    }


def test_line_render__expect_x_and_y_read_from_the_event() -> None:
    chart = LineChart("throughput", source="throughput", x="requests", y="latency")
    events = [
        Event("throughput", {"requests": 120, "latency": 96}),
        Event("throughput", {"requests": 240, "latency": 108}),
    ]

    assert chart.render(events) == {
        "series": ["latency"],
        "x": [120.0, 240.0],
        "y": [[96.0, 108.0]],
    }


def test_line_at_without_the_field__expect_nowhere_to_sit() -> None:
    chart = LineChart("throughput", source="throughput", x="requests")

    assert chart.at(Event("throughput")) is None


def test_render_with_an_unreadable_x__expect_the_row_dropped() -> None:
    chart = LineChart("perf", source="perf", x="requests", y="ms")
    events = [
        Event("perf", {"requests": 120, "ms": 96}),
        Event("perf", {"requests": "many", "ms": 108}),
    ]

    assert chart.render(events) == {
        "series": ["ms"],
        "x": [120.0],
        "y": [[96.0]],
    }


def test_update_with_an_unreadable_x__expect_nothing_to_draw() -> None:
    chart = LineChart("perf", source="perf", x="requests")

    assert chart.update(Event("perf", {"requests": "many"})) is None


def test_value_of_something_unreadable__expect_a_gap() -> None:
    chart = TimeSeriesChart("latency", source="latency")

    assert chart.value(Event("latency", {"value": "fast"}), "value") is None


def test_value_of_a_field_the_event_lacks__expect_a_gap() -> None:
    chart = TimeSeriesChart("latency", source="latency")

    assert chart.value(Event("latency", {"ms": 96}), "value") is None


def test_render_with_an_unreadable_value__expect_a_gap_in_the_line() -> None:
    chart = TimeSeriesChart("latency", source="latency")
    now = datetime.now(tz=timezone.utc)
    events = [
        Event("latency", {"value": 96}, at=now - timedelta(seconds=1)),
        Event("latency", {"value": "fast"}, at=now),
    ]

    assert chart.render(events)["y"] == [[96.0, None]]


def test_render_with_one_unreadable_series__expect_the_others_kept() -> None:
    chart = TimeSeriesChart("perf", source="perf", y=["p50", "p95"])

    assert chart.render([Event("perf", {"p50": 10, "p95": "slow"})])["y"] == [
        [10.0],
        [None],
    ]


def test_warn__expect_one_line_however_often_the_field_arrives(
    caplog: pytest.LogCaptureFixture,
) -> None:
    chart = TimeSeriesChart("latency", source="latency")

    with caplog.at_level(logging.WARNING, logger="dachshund"):
        for _ in range(5):
            chart.value(Event("latency", {"value": "fast"}), "value")

    assert caplog.text.count("is not a number") == 1


def test_bar_render__expect_a_total_per_category() -> None:
    chart = BarChart("weight", source="weight", x="name", y="ms")
    events = [
        Event("weight", {"name": "/ban", "ms": 96}),
        Event("weight", {"name": "/help", "ms": 4}),
        Event("weight", {"name": "/ban", "ms": 4}),
    ]

    assert chart.render(events) == {
        "series": ["ms"],
        "x": ["/ban", "/help"],
        "y": [[100.0, 4.0]],
    }


def test_bar_counting__expect_the_emitted_ones_totalled() -> None:
    chart = BarChart("commands", source="commands", x="name")
    events = [
        Event("commands", {"name": "/ban", "value": 1}),
        Event("commands", {"name": "/ban", "value": 1}),
        Event("commands", {"name": "/help", "value": 1}),
    ]

    assert chart.render(events) == {
        "series": ["value"],
        "x": ["/ban", "/help"],
        "y": [[2.0, 1.0]],
    }


def test_bar_render_without_the_category__expect_one_unlabelled_bar() -> None:
    chart = BarChart("commands", source="commands", x="name")

    assert chart.render([Event("commands", {"value": 1})]) == {
        "series": ["value"],
        "x": ["—"],
        "y": [[1.0]],
    }


def test_bar_render_with_an_unreadable_value__expect_it_left_out() -> None:
    chart = BarChart("weight", source="weight", x="name", y="ms")
    events = [
        Event("weight", {"name": "/ban", "ms": 96}),
        Event("weight", {"name": "/ban", "ms": "slow"}),
    ]

    assert chart.render(events) == {
        "series": ["ms"],
        "x": ["/ban"],
        "y": [[96.0]],
    }


def test_bar_render_of_an_event_carrying_nothing__expect_it_left_out() -> None:
    chart = BarChart("commands", source="commands", x="name")

    assert chart.render([Event("commands", {"name": "/ban"})]) == {
        "series": ["value"],
        "x": [],
        "y": [[]],
    }


def test_bar_accumulate_without_persist__expect_nothing_kept() -> None:
    chart = BarChart("commands", source="commands", x="name")

    chart.accumulate(Event("commands", {"name": "/ban", "value": 1}))

    assert chart.state.entries == {}
    assert chart.snapshot() is None


def test_bar_accumulate_with_persist__expect_the_totals_kept() -> None:
    chart = BarChart("commands", source="commands", x="name", persist=True)

    chart.accumulate(Event("commands", {"name": "/ban", "value": 1}))
    chart.accumulate(Event("commands", {"name": "/ban", "value": 1}))
    chart.accumulate(Event("commands", {"name": "/help", "value": 1}))

    assert chart.state.entries == {"/ban": 2.0, "/help": 1.0}
    assert chart.snapshot() == chart.state.snapshot()


def test_bar_accumulate_with_an_unreadable_value__expect_it_skipped() -> None:
    chart = BarChart("weight", source="weight", x="name", y="ms", persist=True)

    chart.accumulate(Event("weight", {"name": "/ban", "ms": "slow"}))

    assert chart.state.entries == {}


def test_bar_accumulate_with_delete__expect_the_category_dropped() -> None:
    chart = BarChart("commands", source="commands", x="name", persist=True)
    chart.accumulate(Event("commands", {"name": "/ban", "value": 1}))

    chart.accumulate(Event("commands", {"name": "/ban", "_delete": True}))

    assert chart.state.entries == {}


def test_bar_sweep__expect_untouched_categories_dropped() -> None:
    chart = BarChart("commands", source="commands", x="name", persist=True)
    chart.accumulate(Event("commands", {"name": "/ban", "value": 1}, at=_at(1.0)))
    chart.accumulate(Event("commands", {"name": "/help", "value": 1}, at=_at(5.0)))

    chart.sweep(before=3.0)

    assert chart.state.entries == {"/help": 1.0}


def test_bar_restore__expect_the_totals_seeded() -> None:
    chart = BarChart("commands", source="commands", x="name", persist=True)

    chart.restore({"entries": {"/ban": 4.0}, "seen_at": {}})

    assert chart.state.entries == {"/ban": 4.0}


def test_bar_render_with_persist__expect_the_kept_totals_not_the_events() -> None:
    chart = BarChart("commands", source="commands", x="name", persist=True)
    chart.restore({"entries": {"/ban": 4.0}, "seen_at": {}})

    # A stale event, ignored: a persisting chart reads its own kept totals.
    events = [Event("commands", {"name": "/help", "value": 1})]

    assert chart.render(events) == {
        "series": ["value"],
        "x": ["/ban"],
        "y": [[4.0]],
    }


def test_number_type_and_op__expect_a_full_replace() -> None:
    assert (Number.type, Number.op) == ("number", "replace")


def test_number_script_and_style__expect_them_set() -> None:
    assert Number.script is not None and Number.script.is_file()
    assert Number.style is not None and Number.style.is_file()


def test_number_render_without_events__expect_no_value() -> None:
    widget = Number("highest_latency", source="highest_latency")

    assert widget.render([]) == {"value": None, "unit": None}


def test_number_render__expect_the_latest_event_not_a_total() -> None:
    widget = Number("highest_latency", source="highest_latency")
    events = [
        Event("highest_latency", {"value": 96}),
        Event("highest_latency", {"value": 108}),
    ]

    assert widget.render(events) == {"value": 108.0, "unit": None}


def test_number_render_with_a_custom_field__expect_it_read_instead() -> None:
    widget = Number("cpu", source="cpu", y="load")

    assert widget.render([Event("cpu", {"load": 42})]) == {"value": 42.0, "unit": None}


def test_number_render_with_an_unreadable_value__expect_no_value() -> None:
    widget = Number("highest_latency", source="highest_latency")

    assert widget.render([Event("highest_latency", {"value": "fast"})]) == {
        "value": None,
        "unit": None,
    }


def test_number_render_with_a_unit__expect_it_carried_through() -> None:
    widget = Number("highest_latency", source="highest_latency", unit="ms")

    assert widget.render([Event("highest_latency", {"value": 96})]) == {
        "value": 96.0,
        "unit": "ms",
    }


def test_number_accumulate_without_persist__expect_nothing_kept() -> None:
    widget = Number("highest_latency", source="highest_latency")

    widget.accumulate(Event("highest_latency", {"value": 96}))

    assert widget.kept is None
    assert widget.snapshot() is None


def test_number_accumulate_with_persist__expect_the_reading_kept() -> None:
    widget = Number("highest_latency", source="highest_latency", persist=True)

    widget.accumulate(Event("highest_latency", {"value": 96}))
    widget.accumulate(Event("highest_latency", {"value": 108}))

    assert widget.kept == {"value": 108.0}
    assert widget.snapshot() == {"value": 108.0}


def test_number_accumulate_with_an_unreadable_value__expect_it_skipped() -> None:
    widget = Number("highest_latency", source="highest_latency", persist=True)

    widget.accumulate(Event("highest_latency", {"value": "fast"}))

    assert widget.kept is None


def test_number_restore__expect_the_reading_seeded() -> None:
    widget = Number("highest_latency", source="highest_latency", persist=True)

    widget.restore({"value": 96.0})

    assert widget.kept == {"value": 96.0}


def test_number_render_with_persist__expect_the_kept_reading_not_the_events() -> None:
    widget = Number("highest_latency", source="highest_latency", persist=True)
    widget.restore({"value": 96.0})

    # A stale event, ignored: a persisting widget reads its own kept reading.
    events = [Event("highest_latency", {"value": 1})]

    assert widget.render(events) == {"value": 96.0, "unit": None}


def test_number_render_with_persist_and_nothing_kept__expect_no_value() -> None:
    widget = Number("highest_latency", source="highest_latency", persist=True)

    assert widget.render([]) == {"value": None, "unit": None}


def test_button_type_and_op__expect_a_full_replace() -> None:
    assert (Button.type, Button.op) == ("button", "replace")


def test_button_script_and_style__expect_neither_set() -> None:
    assert Button.script is None
    assert Button.style is None


def test_button_render__expect_nothing_to_show() -> None:
    widget = Button("ban", source="ban", actions=["ban"])

    assert widget.render([Event("ban", {"user": "ada"})]) == {}


def test_button_update__expect_nothing_ever_changes() -> None:
    widget = Button("ban", source="ban")

    assert widget.update(Event("ban", {"user": "ada"})) is None


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
