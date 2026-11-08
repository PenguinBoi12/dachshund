import json
from datetime import datetime, timedelta, timezone
from typing import Any

UNITS = (("day", 86400), ("hour", 3600), ("minute", 60))


def since(moment: datetime) -> str:
    """Spell out how long ago something happened.

    Naive datetimes are read as local time.

    ## Example

    ```html
    <span>online · {{ service.started_at|since }}</span>
    ```
    """
    if moment.tzinfo is None:
        moment = moment.astimezone()

    return humanize(datetime.now(tz=timezone.utc) - moment)


def timestamp(moment: datetime) -> str:
    """Spell out an exact moment, for the tooltip behind a relative time.

    Naive datetimes are read as local time. The zone is always shown, so the
    reading is never ambiguous.

    ## Example

    ```html
    <span title="{{ service.started_at|timestamp }}">
      {{ service.started_at|since }}
    </span>
    ```

    ```python
    timestamp(datetime(2026, 8, 8, 9, 12, tzinfo=timezone.utc))
    # "Aug 8, 2026 at 09:12 UTC"
    ```
    """
    if moment.tzinfo is None:
        moment = moment.astimezone()

    return f"{moment:%b} {moment.day}, {moment:%Y} at {moment:%H:%M %Z}"


def humanize(duration: timedelta) -> str:
    """Spell out a duration in its largest whole unit.

    ## Example

    ```python
    humanize(timedelta(days=41))  # "41 days"
    ```
    """
    seconds = int(duration.total_seconds())

    for unit, size in UNITS:
        count = seconds // size

        if count:
            return f"{count} {unit}" if count == 1 else f"{count} {unit}s"

    return "just now"


def tojson(value: Any) -> str:
    """A value as JSON, for embedding in an HTML attribute.

    Autoescaping still runs on the result, so this is safe inside a quoted
    attribute (`data-args="{{ value|tojson }}"`) without anything extra.

    ## Example

    ```html
    <button data-args="{{ action.args|tojson }}">{{ action.label }}</button>
    ```
    """
    return json.dumps(value)


FILTERS = {
    "since": since,
    "timestamp": timestamp,
    "tojson": tojson,
}
