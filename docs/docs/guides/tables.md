# Tables

A [Table](../reference/table.md) shows rows, searchable, sortable and split into pages. Its rows come from events, or from your own data through a loader.

## Rows from events

By default, every event is a new row:

```python
import dachshund
from dachshund.widgets import Table

with dachshund.row():
    dachshund.add(Table("requests", columns=["route", "status", "ms"]))

dachshund.emit("requests", route="/users", status=200, ms=12)
```

The table holds the latest 500 events of its source, like every widget, see [How long events are kept](widgets.md#how-long-events-are-kept).

## One row per key

With a `key`, an event whose key matches a row replaces it, so the table shows the current state of each thing:

```python
with dachshund.row():
    dachshund.add(Table("sessions", columns=["user", "ip"], key="user"))

dachshund.emit("sessions", user="ada", ip="10.0.0.1")
dachshund.emit("sessions", user="ada", ip="10.0.0.2")  # replaces ada's row
dachshund.emit("sessions", user="ada", _delete=True)  # removes it
```

A keyed table can keep its rows across restarts with `persist=True`, see [Persistent Storage](persistent-storage.md).

## Row actions

A table's `actions` show as a button on every row. The row's fields are passed to the handler by name. A field starting with `_` is hidden from the table, and passed without the underscore:

```python
@dachshund.action("ban", label="Ban", confirm=True)
def ban(ctx, user: str, team_id: str) -> None: ...


with dachshund.row():
    dachshund.add(Table("sessions", columns=["user"], key="user", actions=["ban"]))

dachshund.emit("sessions", user="ada", _team_id="42")
```

See [Actions](actions.md) for how handlers are called.

## Rows from your data

For data that lives elsewhere, like users in a database, give the table a `loader` instead of emitting rows. It's called every time a page of the table is shown, with the dashboard's [context](actions.md#context) and a [TableQuery][dachshund.widgets.query.TableQuery]: the search, the sort, and the offset and limit of the page.

```python
from dachshund.widgets import Table, TableQuery


async def load_users(ctx: AppContext, query: TableQuery):
    users = await ctx.db.users(
        search=query.search,
        order_by=query.sort_by,
        descending=query.descending,
        offset=query.offset,
        limit=query.limit,
    )
    total = await ctx.db.count_users(search=query.search)

    return [{"id": u.id, "name": u.name} for u in users], total


dachshund.init("My service", context=AppContext(db=db))

with dachshund.row():
    dachshund.add(Table("users", columns=["id", "name"], loader=load_users))
```

A loader can be sync or async. It returns the rows of that page and the number of rows matching the search, or `None` when counting them is too costly. Without a total, the table offers a next page as long as a full page comes back.

To refresh a loaded table, emit to its source. The open page of the table is loaded again.
