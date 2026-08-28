from datetime import datetime, timezone

from dachshund.storage.events import Event
from dachshund.widgets.chart.bar import BarChart


def _at(seconds: float) -> datetime:
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


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
