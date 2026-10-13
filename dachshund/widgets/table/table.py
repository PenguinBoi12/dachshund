import asyncio
from dataclasses import KW_ONLY, dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, ClassVar, Sequence

from dachshund.actions import Context, run
from dachshund.storage.events import Event
from dachshund.widgets.state import KeyedWidget

RESERVED = ("_delete",)

PageResult = tuple[list[dict[str, Any]], str | None]
Loader = Callable[[Context, str | None, int], PageResult | Awaitable[PageResult]]


def _fields(payload: dict[str, Any]) -> dict[str, Any]:
    """A row payload's fields, stripped of a leading `_` and reserved keys."""
    return {
        key.lstrip("_"): value for key, value in payload.items() if key not in RESERVED
    }


@dataclass
class Table(KeyedWidget):
    """A row per kept event, `columns` naming which payload fields are shown.

    `key` names a payload field identifying "the same row" across events: an
    event whose `key` field matches an already-kept row replaces it in place
    rather than appending a new one. Left unset, every kept event is its own
    row.

    A row is a snapshot, not a stream: the whole table is rebuilt from the
    kept events on every change, the same way `BarChart` rebuilds its bars.

    With `persist=True`, rows survive a restart. Needs `key` set and
    `storage=...` configured on the dashboard. A truthy `_delete` field
    removes a row instead of updating it:

    ```python
    from dachshund.storage.sqlite import SQLiteStorage

    dachshund.init(storage=SQLiteStorage("widget_state.db"))
    dachshund.widget(
        "sessions", type="table", columns=["user", "ip"], key="user", persist=True
    )
    dachshund.emit("sessions", user="ada", ip="10.0.0.1")
    dachshund.emit("sessions", user="ada", _delete=True)
    ```

    For a table backed by data dachshund doesn't own, `loader` fetches a
    page directly instead: a function of `(ctx, cursor, page_size)`
    returning `(rows, next_cursor)`, sync or async, called every time a
    page is needed, `ctx` is the dashboard's own context, same as an
    action handler's first argument. Mutually exclusive with `persist`, a
    table is either self-contained or fully delegated:

    ```python
    def load_page(ctx, cursor, page_size):
        query = ctx["db"].query(User)
        if cursor is not None:
            query = query.filter(User.id > int(cursor))
        rows = query.order_by(User.id).limit(page_size).all()
        next_cursor = str(rows[-1].id) if len(rows) == page_size else None
        return [{"user": row.name, "ip": row.ip} for row in rows], next_cursor

    dashboard.widget(
        "sessions", type="table", columns=["user", "ip"], loader=load_page
    )
    ```

    `actions` (see [Widget][dachshund.Widget]) render one button per row
    instead of the generic card-level row, since an action here runs against
    a particular row, not the card as a whole. A payload field emitted with a
    leading `_` (`_guild_id`) is left off the rendered table, and reaches an
    action's arguments under its name without the underscore (`guild_id`).

    ## Example

    ```python
    @dachshund.action("ban", label="Ban", confirm=True)
    def ban_user(ctx: dachshund.Context, user: str, guild_id: int) -> None:
        ...

    dachshund.widget(
        "sessions",
        type="table",
        columns=["user", "ip"],
        key="user",
        actions=["ban"],
    )
    dachshund.emit("sessions", user="ada", ip="10.0.0.1", _guild_id=1349086642446532639)
    ```
    """

    _: KW_ONLY

    columns: list[str]
    key: str | None = None
    page_size: int = 5
    loader: Loader | None = None

    type: ClassVar[str] = "table"
    op: ClassVar[str] = "replace"
    renders_own_actions: ClassVar[bool] = True
    paginated: ClassVar[bool] = True
    script: ClassVar[Path] = Path(__file__).parent / "table.js"
    style: ClassVar[Path] = Path(__file__).parent / "table.css"

    def __post_init__(self) -> None:
        super().__post_init__()

        if self.persist and self.key is None:
            raise ValueError(
                f"{self.name!r} wants to persist, but has no key to identify a row by."
            )

        if self.loader is not None and self.persist:
            raise ValueError(
                f"{self.name!r} has both a loader and persist=True; a table is "
                "either self-contained or fully delegated, not both."
            )

    def render(self, events: Sequence[Event]) -> dict[str, Any]:
        """Rebuild every row from the events kept for this source.

        An event carrying `key` replaces the row it matches; one that
        doesn't, or carries no value for it, is always its own row.

        A persisting table reads its own kept rows instead, since those
        cover more than whatever events are still around to rebuild from.
        """
        if self.persist:
            rows = [{"fields": fields} for fields in self.state.entries.values()]
        else:
            rows = []
            by_key: dict[Any, int] = {}

            for event in events:
                fields = _fields(event.payload)

                if self.key is not None and self.key in fields:
                    row_key = fields[self.key]

                    if row_key in by_key:
                        rows[by_key[row_key]] = {"fields": fields}
                        continue

                    by_key[row_key] = len(rows)

                rows.append({"fields": fields})

        shown = [column for column in self.columns if not column.startswith("_")]

        return {"columns": shown, "rows": rows}

    def _row_cursor(self, row: dict[str, Any], index: int) -> str:
        """The cursor identifying `row`.

        A persisting table's cursor is the row's `self.state.sequence`
        (`__post_init__` guarantees `key` is set whenever `persist` is). A
        non-persisting table's cursor is its own key value, or its
        position if it has none.
        """
        if self.persist and self.key is not None:
            identity = str(row["fields"].get(self.key))
            return str(self.state.sequence.get(identity, index))

        if self.key is not None:
            return str(row["fields"].get(self.key, index))

        return str(index)

    def _index_after(self, rows: list[dict[str, Any]], cursor: str | None) -> int:
        if cursor is None:
            return 0

        if self.persist:
            try:
                threshold = int(cursor)
            except ValueError:
                return 0

            for index, row in enumerate(rows):
                if int(self._row_cursor(row, index)) > threshold:
                    return index

            return len(rows)

        for index, row in enumerate(rows):
            if self._row_cursor(row, index) == cursor:
                return index + 1

        # a stale/unknown cursor (its row is gone): start over
        return 0

    async def page(
        self,
        events: Sequence[Event],
        cursor: str | None,
        context: Context,
        host_loop: asyncio.AbstractEventLoop | None = None,
    ) -> dict[str, Any]:
        """One page of this table's rows, starting after `cursor`.

        `cursor` is `None` for the first page. A `loader` answers directly,
        sync or async; see `run()`.
        """
        if self.loader is not None:
            rows, next_cursor = await run(
                self.loader, context, cursor, self.page_size, host_loop=host_loop
            )

            return {
                "columns": [c for c in self.columns if not c.startswith("_")],
                "rows": [{"fields": _fields(row)} for row in rows],
                "next_cursor": next_cursor,
                "page_size": self.page_size,
            }

        built = self.render(events)
        rows = built["rows"]
        start = self._index_after(rows, cursor)
        page_rows = rows[start : start + self.page_size]
        end = start + len(page_rows)
        next_cursor = (
            self._row_cursor(page_rows[-1], end - 1) if end < len(rows) else None
        )

        return {
            "columns": built["columns"],
            "rows": page_rows,
            "next_cursor": next_cursor,
            "page_size": self.page_size,
        }

    def accumulate(self, event: Event) -> None:
        """Fold one more event into the kept rows, if persisting.

        A truthy `_delete` removes the row instead of updating it.
        """
        if not self.persist or self.key is None:
            return

        if self.key not in event.payload:
            self.warn(self.key, None)
            return

        row_key = event.payload[self.key]

        if event.payload.get("_delete"):
            self.state.remove(row_key)
            return

        self.state.upsert(row_key, _fields(event.payload), event.at.timestamp())
