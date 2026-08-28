from dachshund.storage.events import Event
from dachshund.widgets.number.number import Number


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
