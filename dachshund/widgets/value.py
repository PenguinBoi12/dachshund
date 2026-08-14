import math
from datetime import datetime, timedelta
from decimal import InvalidOperation
from typing import Any


def numeric(value: Any) -> float | None:
    """Read a value as a number, or `None` when it is not one.

    Datetimes read as their timestamp and durations as their seconds, so both
    can be plotted without the application converting them first.

    Infinities and `nan` are not numbers here: `json.dumps` writes them as
    bare `NaN` and `Infinity`, which no browser will parse back.

    ## Example

    ```python
    numeric(96)              # 96.0
    numeric("96")            # 96.0
    numeric(timedelta(3))    # 259200.0
    numeric("fast")          # None
    ```
    """
    if value is None or isinstance(value, (str, bytes)) and not value.strip():
        return None

    if isinstance(value, datetime):
        return value.timestamp()

    if isinstance(value, timedelta):
        return value.total_seconds()

    try:
        number = float(value)
    except (TypeError, ValueError, InvalidOperation):
        return None

    return number if math.isfinite(number) else None
