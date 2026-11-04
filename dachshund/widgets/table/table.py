import asyncio
from dataclasses import KW_ONLY, dataclass, field, replace
from pathlib import Path
from typing import Any, Awaitable, Callable, ClassVar, Sequence

from dachshund.actions import Context, run
from dachshund.storage.events import Event
from dachshund.widgets.query import TableQuery
from dachshund.widgets.state import KeyedWidget

RESERVED = ("_delete",)

PageResult = tuple[list[dict[str, Any]], int | None]


Loader = Callable[[Context, TableQuery], PageResult | Awaitable[PageResult]]


def _sort_key(value: Any) -> tuple[int, Any]:
    """Numbers before text, each in its own order, so mixed columns still sort."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return (0, value)

    return (1, str(value).lower())


def _fields(payload: dict[str, Any]) -> dict[str, Any]:
    """A row payload's fields, stripped of a leading `_` and reserved keys."""
    return {
        key.lstrip("_"): value for key, value in payload.items() if key not in RESERVED
    }


@dataclass
class Table(KeyedWidget):
    """A searchable, sortable table, one row per kept event.

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
    - `page_size` (`int`) - Rows per page. Defaults to `10`.
    - `search` (`bool`) - Shows a search box. Defaults to `True`.
    - `sortable` (`list[str]`) - Columns sorted by clicking their header.
      Defaults to every shown column.
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
    def ban(ctx, user: str, team_id: str) -> None: ...

    dachshund.add(Table("sessions", columns=["user"], key="user", actions=["ban"]))
    dachshund.emit("sessions", user="ada", _team_id="42")
    ```

    A truthy `_delete` field removes the row with that key.

    ## Loader

    A function of `(ctx, query)`, sync or async, returning `(rows, total)`.
    `query` is a [TableQuery][dachshund.widgets.query.TableQuery]: apply its search, sort,
    offset and limit, and return that page. `total` is the number of rows
    matching the search, or `None` when counting them is too costly. It's
    called every time a page is shown.

    ```python
    def load_users(ctx, query):
        users = ctx["db"].users(search=query.search, order_by=query.sort_by)
        page = users[query.offset : query.offset + query.limit]

        return page, len(users)

    dachshund.add(Table("users", columns=["name", "email"], loader=load_users))
    ```

    ## Pagination

    Pages move by offset, showing "11-20 of 412". Without a total, the next
    page is offered while a full page comes back. A live update refreshes the
    page shown, so rows can shift across pages as they change.
    """

    _: KW_ONLY

    columns: list[str]
    key: str | None = None
    page_size: int = 10
    loader: Loader | None = None
    search: bool = True
    sortable: list[str] | None = field(default=None)

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

        unknown = [c for c in self.sortable or [] if c not in self.columns]

        if unknown:
            raise ValueError(
                f"{self.name!r} sorts by columns it doesn't show: {', '.join(unknown)}."
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

        return {"columns": self.shown, "rows": rows}

    @property
    def shown(self) -> list[str]:
        """The columns drawn, hidden `_` ones left out."""
        return [column for column in self.columns if not column.startswith("_")]

    @property
    def sortable_columns(self) -> list[str]:
        """The columns whose header sorts the table."""
        return self.shown if self.sortable is None else list(self.sortable)

    def query(
        self, rows: list[dict[str, Any]], query: TableQuery
    ) -> list[dict[str, Any]]:
        """`rows` matching `query`'s search, in its order. No page is cut."""
        if query.search:
            needle = query.search.lower()
            rows = [
                row
                for row in rows
                if any(
                    needle in str(row["fields"].get(column, "")).lower()
                    for column in self.shown
                )
            ]

        if query.sort_by in self.sortable_columns:
            column = query.sort_by
            present = [row for row in rows if row["fields"].get(column) is not None]
            missing = [row for row in rows if row["fields"].get(column) is None]
            present.sort(key=lambda row: _sort_key(row["fields"][column]))

            if query.descending:
                present.reverse()

            rows = present + missing

        return rows

    async def page(
        self,
        events: Sequence[Event],
        query: TableQuery,
        context: Context,
        host_loop: asyncio.AbstractEventLoop | None = None,
    ) -> dict[str, Any]:
        """One page of this table's rows, as `query` asks for.

        A `loader` answers directly, sync or async; see `run()`.
        """
        limit = query.limit or self.page_size
        query = replace(query, limit=limit)

        if self.loader is not None:
            loaded, total = await run(self.loader, context, query, host_loop=host_loop)
            rows = [{"fields": _fields(row)} for row in loaded]
        else:
            matching = self.query(self.render(events)["rows"], query)
            total = len(matching)
            rows = matching[query.offset : query.offset + limit]

        return {
            "columns": self.shown,
            "rows": rows,
            "total": total,
            "offset": query.offset,
            "limit": limit,
            "sortable": self.sortable_columns,
            "search": self.search,
            "sort_by": query.sort_by,
            "descending": query.descending,
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
