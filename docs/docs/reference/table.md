# Table

`Table` draws a row per kept event. `columns` names which payload fields become columns, and `key` names a field identifying "the same row" across events: an event whose `key` field matches an already-kept row replaces it in place instead of appending a new one.

```python
import dachshund

dachshund.widget("sessions", type="table", columns=["user", "ip"], key="user")
dachshund.emit("sessions", user="ada", ip="10.0.0.1")
```

`actions` (see [Actions](actions.md)) render one button per row instead of the card's usual button row, since an action here runs against a particular row:

```python
@dachshund.action("ban", label="Ban", confirm=True)
def ban_user(ctx: dachshund.Context, user: str) -> None:
    ...

dachshund.widget(
    "sessions",
    type="table",
    columns=["user", "ip"],
    key="user",
    actions=["ban"],
)
```

A field emitted with a leading `_` (`_guild_id`) is left off the rendered table, and reaches an action's arguments under its name without the underscore (`guild_id`):

```python
@dachshund.action("ban", label="Ban", confirm=True)
def ban_user(ctx: dachshund.Context, user: str, guild_id: int) -> None:
    ...

dachshund.emit("sessions", user="ada", ip="10.0.0.1", _guild_id=1349086642446532639)
```

The server paginates rows, 5 to a page (`page_size` to change it), with a "‹ ›" control under the table once there's more than one page. Paging is forward-only by cursor, not by page number, there's no total shown, since one isn't needed to page through. There's nothing else to configure. A cursor is the row's own key (or its position, if the table has none), so it can lose its place if that specific row is gone by the next fetch, falling back to the start; `persist=True` below changes this.

With `persist=True`, rows survive a restart. Needs `key` set and `storage=...` configured on the dashboard. This also changes what a cursor is: instead of the row's own key, it's the row's insertion order, which never changes once assigned, so paging stays correct through any add, update, or delete, including a live update that removes the exact row a page boundary landed on:

```python
from dachshund.storage.sqlite import SQLiteStorage

dashboard = Dashboard(storage=SQLiteStorage("widget_state.db"))
members = dashboard.widget(
    "sessions", type="table", columns=["user", "ip"], key="user", persist=True
)
dashboard.emit("sessions", user="ada", ip="10.0.0.1")
```

A truthy `_delete` field removes a row instead of updating it:

```python
dashboard.emit("sessions", user="ada", _delete=True)
```

`sweep(before)` drops any row not touched since a given time, for resyncing after downtime, re-emit every currently-known row, then sweep:

```python
members.sweep(before=time.time())
```

::: dachshund.widgets.table.table.Table
