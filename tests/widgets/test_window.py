from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from dachshund.widgets.window import boundaries, since

TORONTO = ZoneInfo("America/Toronto")
UTC = ZoneInfo("UTC")


def local(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=TORONTO)


def test_since_without_over__expect_everything() -> None:
    assert since(None, datetime.now(tz=timezone.utc), UTC) is None


def test_since_with_a_timedelta__expect_that_long_ago() -> None:
    now = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)

    assert since(timedelta(hours=1), now, UTC) == (now - timedelta(hours=1)).timestamp()


@pytest.mark.parametrize(
    "period, expected",
    [
        ("day", local(2026, 11, 6)),
        ("week", local(2026, 11, 2)),
        ("month", local(2026, 11, 1)),
    ],
)
def test_since_with_a_period__expect_its_local_start(
    period: str, expected: datetime
) -> None:
    now = local(2026, 11, 6, 15, 30)

    assert since(period, now, TORONTO) == expected.timestamp()  # type: ignore[arg-type]


def test_since_day_near_utc_midnight__expect_the_local_day() -> None:
    # 01:00 UTC on the 7th is still the evening of the 6th in Toronto.
    now = datetime(2026, 11, 7, 1, tzinfo=timezone.utc)

    assert since("day", now, TORONTO) == local(2026, 11, 6).timestamp()


def test_boundaries_without_every__expect_one_bucket() -> None:
    assert boundaries(100.0, 500.0, None, UTC, 500) == [100.0, 500.0]
    assert boundaries(None, 500.0, None, UTC, 500) == [0.0, 500.0]


def test_boundaries_of_minutes__expect_whole_minutes_up_to_now() -> None:
    edges = boundaries(130.0, 300.0, timedelta(minutes=1), UTC, 500)

    assert edges == [120.0, 180.0, 240.0, 300.0]


def test_boundaries_without_start__expect_the_latest_limit_buckets() -> None:
    edges = boundaries(None, 600.0, timedelta(minutes=1), UTC, 3)

    assert edges == [420.0, 480.0, 540.0, 600.0]


def test_boundaries_of_days_across_dst__expect_local_midnights() -> None:
    # Toronto falls back on 2026-11-01: that day lasts 25 hours.
    start = local(2026, 10, 31, 12).timestamp()
    end = local(2026, 11, 2, 12).timestamp()

    edges = boundaries(start, end, timedelta(days=1), TORONTO, 500)

    assert edges == [
        local(2026, 10, 31).timestamp(),
        local(2026, 11, 1).timestamp(),
        local(2026, 11, 2).timestamp(),
        end,
    ]
    assert edges[2] - edges[1] == 25 * 3600


def test_boundaries_of_days_without_start__expect_the_latest_limit_days() -> None:
    end = local(2026, 11, 6, 12).timestamp()

    edges = boundaries(None, end, timedelta(days=1), TORONTO, 3)

    assert edges == [
        local(2026, 11, 4).timestamp(),
        local(2026, 11, 5).timestamp(),
        local(2026, 11, 6).timestamp(),
        end,
    ]
