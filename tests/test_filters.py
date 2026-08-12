from datetime import datetime, timedelta, timezone

import pytest

from dachshund.filters import humanize, since, timestamp
from dachshund.runtime.http import create_environment


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        (timedelta(seconds=4), "just now"),
        (timedelta(minutes=1), "1 minute"),
        (timedelta(minutes=42), "42 minutes"),
        (timedelta(hours=1, minutes=30), "1 hour"),
        (timedelta(days=41), "41 days"),
    ],
)
def test_humanize__expect_the_largest_whole_unit(
    duration: timedelta, expected: str
) -> None:
    assert humanize(duration) == expected


def test_since__expect_the_time_elapsed() -> None:
    moment = datetime.now(tz=timezone.utc) - timedelta(hours=3)

    assert since(moment) == "3 hours"


def test_since_with_a_naive_datetime__expect_it_read_as_local_time() -> None:
    moment = datetime.now() - timedelta(days=2)

    assert since(moment) == "2 days"


def test_environment_filters__expect_them_registered() -> None:
    template = create_environment().from_string("{{ moment|since }}")
    moment = datetime.now(tz=timezone.utc) - timedelta(minutes=5)

    assert template.render(moment=moment) == "5 minutes"


def test_timestamp__expect_an_exact_moment() -> None:
    moment = datetime(2026, 8, 8, 9, 12, tzinfo=timezone.utc)

    assert timestamp(moment) == "Aug 8, 2026 at 09:12 UTC"


def test_timestamp_with_a_naive_datetime__expect_a_zone_shown() -> None:
    moment = datetime(2026, 8, 8, 9, 12)

    assert timestamp(moment).startswith("Aug 8, 2026 at 09:12 ")
