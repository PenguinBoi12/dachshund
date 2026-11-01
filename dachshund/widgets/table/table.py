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
    """A paginated table, one row per kept event.

    ## Example

    ```python
    dachshund.add(Table("sessions", columns=["user", "ip"], key="user"))
    dachshund.emit("sessions", user="ada", ip="10.0.0.1")
    ```

    ## Options

    - `columns` (`list[str]`) - The payload fields shown, left to right.
      Required.
    - `key` (`str`) - The field identifying a row across events. An event
      whose key matches a kept row replaces it. Defaults to `None`, every
      event is a new row.
    - `page_size` (`int`) - Rows per page. Defaults to `5`.
    - `loader` (`Loader`) - Fetches rows from data dachshund doesn't own,
      see [Loader](#loader). Defaults to `None`.
    - `persist` (`bool`) - Keeps rows across restarts. Needs `key` and the
      dashboard's `storage`. Can't be combined with `loader`. Defaults to
      `False`.
    - `actions` (`list[str]`) - Actions shown as a button on every row.
      Defaults to `[]`.

    `source`, `title` and `action_args` are common to every widget, see
    [Widget][dachshund.Widget].

    ## Row fields

    A field starting with `_` is hidden from the table and passed to the
    row's actions without the underscore:

    ```python
    @dachshund.action("ban", label="Ban", confirm=True)
    def ban(ctx, user: str, guild_id: str) -> None: ...

    dachshund.add(Table("sessions", columns=["user"], key="user", actions=["ban"]))
    dachshund.emit("sessions", user="ada", _guild_id="1349086642446532639")
    ```

    A truthy `_delete` field removes the row with that key.

    ## Loader

    A function of `(ctx, cursor, page_size)`, sync or async, returning
    `(rows, next_cursor)`. `cursor` is `None` for the first page and
    `next_cursor` is `None` on the last one. It's called every time a page
    is shown.

    ```python
    def load_users(ctx, cursor, page_size):
        start = int(cursor or 0)
        rows = ctx["db"].users(offset=start, limit=page_size)
        more = len(rows) == page_size
        return rows, str(start + page_size) if more else None

    dachshund.add(Table("users", columns=["name", "email"], loader=load_users))
    ```

    ## Pagination

    Pages move forward by cursor. A kept table's cursor is the last row's
    key, or its position without one, and falls back to the first page if
    that row is gone. With `persist=True`, the cursor is the row's insertion
    order, which stays valid through any update or removal.
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
        """Fold one more event into the kept rows.

        A truthy `_delete` removes the row instead of updating it.
        """
        if self.key is None:
            return

        if self.key not in event.payload:
            self.warn(self.key, None)
            return

        row_key = event.payload[self.key]

        if event.payload.get("_delete"):
            self.state.remove(row_key)
            return

        self.state.upsert(row_key, _fields(event.payload), event.at.timestamp())
