from dataclasses import dataclass, field
from typing import Any

import pytest

from dachshund.storage.events import Event
from dachshund.widgets.base import Widget
from dachshund.widgets.button.button import Button
from dachshund.widgets.chart.bar import BarChart
from dachshund.widgets.chart.line import LineChart
from dachshund.widgets.number.number import Number
from dachshund.widgets.persistable import PersistableWidget, persisting
from dachshund.widgets.table.table import Table
from dachshund.widgets.text.text import Text


@dataclass
class Counter(PersistableWidget):
    total: int = field(default=0, init=False)

    def accumulate(self, event: Event) -> None:
        self.total += 1

    def snapshot(self) -> dict[str, Any]:
        return {"total": self.total}

    def restore(self, data: dict[str, Any]) -> None:
        self.total = data["total"]


def test_a_complete_subclass__expect_persist_off_by_default() -> None:
    assert Counter("hits", source="hits").persist is False


def test_a_subclass_missing_a_hook__expect_type_error() -> None:
    @dataclass
    class Forgetful(PersistableWidget):
        def accumulate(self, event: Event) -> None: ...

        def snapshot(self) -> dict[str, Any]:
            return {}

    with pytest.raises(TypeError, match="restore"):
        Forgetful("hits", source="hits", persist=True)  # type: ignore[abstract]


def test_builtin_widgets__expect_only_stateful_ones_persistable() -> None:
    for cls in (Number, Text, BarChart, Table):
        assert issubclass(cls, PersistableWidget)

    for cls in (LineChart, Button):
        assert not issubclass(cls, PersistableWidget)


def test_persisting_of_a_plain_widget__expect_false() -> None:
    assert not persisting(Widget("latency", source="latency"))


def test_persisting_without_persist__expect_false() -> None:
    assert not persisting(Counter("hits", source="hits"))


def test_persisting_with_persist__expect_true() -> None:
    assert persisting(Counter("hits", source="hits", persist=True))
