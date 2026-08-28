import time
from dataclasses import KW_ONLY, dataclass, field
from typing import Any

from dachshund.widgets.base import Widget


@dataclass
class KeyedState:
    """A dict of entries, keyed by string, with staleness tracking.

    `sequence` names the order each entry was first seen in, once assigned
    it never changes, an update doesn't move it and nothing else being
    added or removed does either. It's what a cursor into this state is
    built from, so paging through it stays correct even past a deletion.
    """

    entries: dict[str, Any] = field(default_factory=dict)
    seen_at: dict[str, float] = field(default_factory=dict)
    sequence: dict[str, int] = field(default_factory=dict)

    _next_sequence: int = field(default=0, init=False, repr=False, compare=False)

    def upsert(self, key: Any, value: Any, at: float | None = None) -> None:
        key = str(key)

        if key not in self.entries:
            self.sequence[key] = self._next_sequence
            self._next_sequence += 1

        self.entries[key] = value
        self.seen_at[key] = time.time() if at is None else at

    def remove(self, key: Any) -> None:
        key = str(key)
        self.entries.pop(key, None)
        self.seen_at.pop(key, None)
        self.sequence.pop(key, None)

    def sweep(self, before: float) -> None:
        """Remove every entry not seen since `before`."""
        for key in [k for k, seen in self.seen_at.items() if seen < before]:
            self.remove(key)

    def snapshot(self) -> dict[str, Any]:
        return {
            "entries": self.entries,
            "seen_at": self.seen_at,
            "sequence": self.sequence,
        }

    def restore(self, data: dict[str, Any]) -> None:
        self.entries = dict(data.get("entries", {}))
        self.seen_at = dict(data.get("seen_at", {}))
        self.sequence = dict(data.get("sequence", {}))
        self._next_sequence = max(self.sequence.values(), default=-1) + 1


@dataclass
class KeyedWidget(Widget):
    """A `Widget` whose persisted state is a `KeyedState`.

    Provides `persist`, `state`, `snapshot`, `restore`, and `sweep`. A
    subclass adds its own `accumulate()` and reads `self.state.entries` in
    `render()`, same as `Table`/`BarChart` do.
    """

    _: KW_ONLY

    persist: bool = False

    state: KeyedState = field(
        default_factory=KeyedState, init=False, repr=False, compare=False
    )

    def snapshot(self) -> dict[str, Any] | None:
        """The kept entries, or `None` when this widget isn't persisting."""
        return self.state.snapshot() if self.persist else None

    def restore(self, data: dict[str, Any]) -> None:
        """Pick up where the last persisted snapshot left off."""
        self.state.restore(data)

    def sweep(self, before: float) -> None:
        """Drop any persisted entry not touched since `before` (a `time.time()` value).

        For resyncing after downtime: re-emit every currently-known entry
        (as already normal), then call this to drop whatever wasn't touched.
        """
        self.state.sweep(before)
