import logging
import queue

from dachshund.storage.events import Event

QUEUE_SIZE = 10_000

logger = logging.getLogger("dachshund")


class EventQueue:
    """Emitted events waiting for the pump, from any thread.

    When full, new events are dropped and counted in `dropped`, with one
    warning per streak of drops.
    """

    def __init__(self, size: int = QUEUE_SIZE) -> None:
        self.size = size
        self.dropped = 0
        self._queue: queue.Queue[Event] = queue.Queue(maxsize=size)
        self._dropping = False

    def put(self, event: Event) -> None:
        """Queue `event` without blocking, or drop it when the queue is full."""
        try:
            self._queue.put_nowait(event)
            self._dropping = False
        except queue.Full:
            self.dropped += 1

            if not self._dropping:
                self._dropping = True
                logger.warning(
                    "The event queue is full (%d slots), dropping events until "
                    "it drains. %d dropped so far.",
                    self.size,
                    self.dropped,
                )

    def drain(self) -> list[Event]:
        """Every queued event, oldest first, taken off the queue."""
        drained = []

        while True:
            try:
                drained.append(self._queue.get_nowait())
            except queue.Empty:
                return drained
