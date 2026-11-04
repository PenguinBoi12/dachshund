# Bigger Dashboard

As a dashboard grows, keeping every page in one file gets hard to follow. A [Page](../reference/page.md) is a plain object built at import, so each one can live in a module of its own.

Here's an example structure:

```
.
├─ myapp
│  ├─ __init__.py
│  ├─ main.py
│  └─ dashboard
│     ├─ __init__.py
│     ├─ dashboard.py
│     ├─ loaders.py
│     └─ pages
│        ├─ __init__.py
│        ├─ overview.py
│        └─ activity.py
```

`dashboard.py` is the dashboard's entry point: it includes every page and starts the dashboard. Each module in `pages/` defines one page, with the actions its widgets use. This is one way to lay it out, pages fit whatever structure works for your project.

## A page module

```python
# myapp/dashboard/pages/overview.py
from dachshund import Number, Page, Table, Text, TimeSeriesChart

from myapp.dashboard.loaders import load_users

overview_page = Page("overview", title="Overview")


@overview_page.action("deactivate", label="Deactivate", confirm=True)
async def deactivate(ctx, id: str) -> None:
    await ctx["db"].deactivate_user(int(id))


with overview_page.row():
    overview_page.add(Text("summary"))
with overview_page.row():
    with overview_page.column(span=4):
        overview_page.add(Number("user_count"))
    overview_page.add(TimeSeriesChart("latency"))
with overview_page.row():
    overview_page.add(
        Table("users", columns=["id", "name", "email"], loader=load_users, actions=["deactivate"])
    )
```

```python
# myapp/dashboard/pages/activity.py
from dachshund import BarChart, Number, Page

activity_page = Page("activity", title="Activity")

with activity_page.row():
    with activity_page.column(span=4):
        activity_page.add(Number("requests_today", title="Requests today"))
    activity_page.add(BarChart("requests_per_day", x="date", persist=True))
with activity_page.row():
    activity_page.add(BarChart("errors_per_route", x="route", persist=True))
```

Code shared by several pages, like a table's loader, goes in a module of its own:

```python
# myapp/dashboard/loaders.py
from dachshund import TableQuery


async def load_users(ctx, query: TableQuery):
    users = await ctx["db"].users(
        search=query.search,
        order_by=query.sort_by,
        descending=query.descending,
        offset=query.offset,
        limit=query.limit,
    )
    total = await ctx["db"].count_users(search=query.search)

    return [{"id": u.id, "name": u.name, "email": u.email} for u in users], total
```

## The entry point

```python
# myapp/dashboard/dashboard.py
import dachshund
from dachshund.storage.sqlite import SQLiteStorage

from myapp.dashboard.pages.activity import activity_page
from myapp.dashboard.pages.overview import overview_page


def start_dashboard(context: dict) -> None:
    dachshund.default(storage=SQLiteStorage("widget_state.db"))  # optional

    for page in (overview_page, activity_page):
        dachshund.include(page)

    dachshund.init("My service", context=context)
```

Your application calls it once at startup:

```python
# myapp/main.py
from myapp.dashboard.dashboard import start_dashboard

start_dashboard(context)
```

`context` is passed as `ctx` to every action and loader, see [Context](../reference/actions.md#context).

Including a page twice does nothing, so `start_dashboard()` can run again after a restart of the dashboard.

## Emitting

Emit from wherever the event happens, not from the dashboard modules:

```python
# myapp/routes.py
import dachshund

def handle(request):
    ...
    dachshund.emit("latency", value=elapsed)
```

## Pages from a library

A library can ship a page the same way, for applications to include:

```python
# dachshund_jobs/pages/jobs.py
from dachshund import Number, Page, Table

jobs_page = Page("jobs", title="Jobs")
with jobs_page.row():
    jobs_page.add(Number("queued_jobs"))
with jobs_page.row():
    jobs_page.add(Table("jobs", columns=["id", "name", "status"], key="id"))
```

```python
from dachshund_jobs.pages.jobs import jobs_page

dachshund.include(jobs_page)
```
