from datetime import datetime, timedelta
from typing import Literal, get_args
from zoneinfo import ZoneInfo

Period = Literal["day", "week", "month"]
PERIODS: tuple[str, ...] = get_args(Period)
DAY = 86400.0


def since(
    over: timedelta | Period | None, now: datetime, zone: ZoneInfo
) -> float | None:
    """Where a window starts: `over` before `now`, or the start of the current period.

    A period starts at local midnight in `zone`: today's, Monday's or the 1st's.
    `None` means everything stored.

    ## Example

    ```python
    since(timedelta(hours=1), now, zone)  # an hour ago
    since("day", now, ZoneInfo("America/Toronto"))  # Toronto's last midnight
    ```
    """
    if over is None:
        return None

    if isinstance(over, timedelta):
        return (now - over).timestamp()

    start = now.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0)

    if over == "week":
        start -= timedelta(days=start.weekday())
    elif over == "month":
        start = start.replace(day=1)

    return start.timestamp()


def boundaries(
    start: float | None,
    end: float,
    every: timedelta | None,
    zone: ZoneInfo,
    limit: int,
) -> list[float]:
    """The edges of the buckets between `start` and `end`, the last bucket ending at `end`.

    Without `every`, one bucket. With it, `start` is rounded down to a whole
    bucket: whole days from local midnight in `zone`, shorter steps from the
    epoch. Without `start`, the latest `limit` buckets. At most `limit` buckets
    are kept, the latest.

    ## Example

    ```python
    boundaries(since, now, None, zone, 500)  # [since, now]
    boundaries(None, now, timedelta(days=1), zone, 7)  # the last 7 local days
    ```
    """
    if every is None:
        return [start if start is not None else 0.0, end]

    step = every.total_seconds()

    if step % DAY == 0:
        edges = _days(start, end, int(step // DAY), zone, limit)
    else:
        first = end - step * limit if start is None else start
        first -= first % step
        edges = []
        edge = first

        while edge < end:
            edges.append(edge)
            edge += step

    return edges[-limit:] + [end]


def _days(
    start: float | None, end: float, days: int, zone: ZoneInfo, limit: int
) -> list[float]:
    def midnight(at: float) -> datetime:
        local = datetime.fromtimestamp(at, tz=zone)
        return local.replace(hour=0, minute=0, second=0, microsecond=0)

    last = midnight(end)
    first = (
        midnight(start)
        if start is not None
        else last - timedelta(days=days * (limit - 1))
    )

    edges = []
    day = first

    # Wall-clock steps, so a day across a DST change lasts 23 or 25 hours.
    while day.timestamp() < end:
        edges.append(day.timestamp())
        day = (day + timedelta(days=days)).replace(tzinfo=zone)

    return edges
