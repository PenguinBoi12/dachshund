from dachshund.storage.events import Event
from dachshund.widgets.button.button import Button


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
