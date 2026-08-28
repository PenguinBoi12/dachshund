from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from dachshund.widgets.value import numeric


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (96, 96.0),
        (96.5, 96.5),
        (0, 0.0),
        (-96, -96.0),
        ("96", 96.0),
        (" 96 ", 96.0),
        ("96.5", 96.5),
        (True, 1.0),
        (False, 0.0),
        (Decimal("96.5"), 96.5),
        (timedelta(seconds=3), 3.0),
        (timedelta(days=1), 86400.0),
        (datetime(2026, 8, 8, tzinfo=timezone.utc), 1786147200.0),
    ],
)
def test_numeric__expect_the_number_it_reads(value: Any, expected: float) -> None:
    assert numeric(value) == expected


@pytest.mark.parametrize(
    "value",
    ["fast", "", "   ", None, [], {}, object(), b"", float("nan")],
)
def test_numeric_of_something_else__expect_none(value: Any) -> None:
    assert numeric(value) is None


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_numeric_of_a_non_finite_float__expect_none(value: float) -> None:
    # json.dumps writes these as bare NaN and Infinity, which no browser parses.
    assert numeric(value) is None
