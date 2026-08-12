from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

DEFAULT_LIMIT = 500


@dataclass(frozen=True)
class Event:
    """Something that happened in the application.

    ## Example

    ```python
    Event("latency", {"value": 96})
    ```
    """

    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


class EventStore:
    """The recent events of every source, kept in memory.

    Only the runtime's event loop touches this, so it needs no locking.
    """

    def __init__(self, limit: int = DEFAULT_LIMIT) -> None:
        self.limit = limit
        self._events: dict[str, deque[Event]] = defaultdict(
            lambda: deque(maxlen=limit),
        )

    def append(self, event: Event) -> None:
        """Keep an event, dropping the oldest one of that source when full."""
        self._events[event.source].append(event)

    def events(self, source: str) -> list[Event]:
        """Every kept event of a source, oldest first."""
        return list(self._events[source])
