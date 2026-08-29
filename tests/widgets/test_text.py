from dachshund.storage.events import Event
from dachshund.widgets.text.text import Text


def test_text_type_and_op__expect_a_full_replace() -> None:
    assert (Text.type, Text.op) == ("text", "replace")


def test_text_script_and_style__expect_them_set() -> None:
    assert Text.script is not None and Text.script.is_file()
    assert Text.style is not None and Text.style.is_file()


def test_text_render_without_events__expect_no_value() -> None:
    widget = Text("changelog", source="changelog")

    assert widget.render([]) == {"html": None}


def test_text_render__expect_the_latest_event_not_the_first() -> None:
    widget = Text("changelog", source="changelog")
    events = [
        Event("changelog", {"value": "first"}),
        Event("changelog", {"value": "**second**"}),
    ]

    assert widget.render(events) == {"html": "<p><strong>second</strong></p>\n"}


def test_text_render_with_a_custom_field__expect_it_read_instead() -> None:
    widget = Text("changelog", source="changelog", y="body")

    assert widget.render([Event("changelog", {"body": "hi"})]) == {
        "html": "<p>hi</p>\n"
    }


def test_text_render_with_a_missing_field__expect_no_value() -> None:
    widget = Text("changelog", source="changelog")

    assert widget.render([Event("changelog", {})]) == {"html": None}


def test_text_render_with_a_script_tag__expect_it_escaped() -> None:
    widget = Text("changelog", source="changelog")
    events = [Event("changelog", {"value": "<script>alert(1)</script>"})]

    assert widget.render(events) == {
        "html": "<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>\n"
    }


def test_text_render_with_a_javascript_link__expect_the_link_dropped() -> None:
    widget = Text("changelog", source="changelog")
    events = [Event("changelog", {"value": "[danger](javascript:alert(1))"})]

    html = widget.render(events)["html"]
    assert html is not None
    assert "<a" not in html


def test_text_accumulate_without_persist__expect_nothing_kept() -> None:
    widget = Text("changelog", source="changelog")

    widget.accumulate(Event("changelog", {"value": "hi"}))

    assert widget.kept is None
    assert widget.snapshot() is None


def test_text_accumulate_with_persist__expect_the_text_kept() -> None:
    widget = Text("changelog", source="changelog", persist=True)

    widget.accumulate(Event("changelog", {"value": "first"}))
    widget.accumulate(Event("changelog", {"value": "second"}))

    assert widget.kept == {"value": "second"}
    assert widget.snapshot() == {"value": "second"}


def test_text_accumulate_with_a_missing_field__expect_it_skipped() -> None:
    widget = Text("changelog", source="changelog", persist=True)

    widget.accumulate(Event("changelog", {}))

    assert widget.kept is None


def test_text_restore__expect_the_text_seeded() -> None:
    widget = Text("changelog", source="changelog", persist=True)

    widget.restore({"value": "hi"})

    assert widget.kept == {"value": "hi"}


def test_text_render_with_persist__expect_the_kept_text_not_the_events() -> None:
    widget = Text("changelog", source="changelog", persist=True)
    widget.restore({"value": "kept"})

    # A stale event, ignored: a persisting widget reads its own kept text.
    events = [Event("changelog", {"value": "stale"})]

    assert widget.render(events) == {"html": "<p>kept</p>\n"}


def test_text_render_with_persist_and_nothing_kept__expect_no_value() -> None:
    widget = Text("changelog", source="changelog", persist=True)

    assert widget.render([]) == {"html": None}
