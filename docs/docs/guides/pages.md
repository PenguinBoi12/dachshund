# Pages

A dashboard is split into pages, each at its own URL and in the navigation. A [Page](../reference/page.md) holds widgets, their layout and actions, and goes on the dashboard with `include()`.

```python
# myapp/dashboard/overview.py
from dachshund import Number, Page, Text, TimeSeriesChart

page = Page("overview", title="Overview")

page.add(Text("summary"))
page.row(
    TimeSeriesChart("latency", y=["check", "command"]),
    page.column(Number("errors"), Number("users")),
    widths=(2, 1),
)


@page.action("flush", label="Flush cache")
def flush(ctx) -> None:
    ctx["cache"].clear()
```

```python
# myapp/main.py
import dachshund
from myapp.dashboard import overview

dachshund.include(overview.page)
dachshund.init("My service", context={"cache": cache})
```

Widget and action names are unique across the dashboard. `include()` adds nothing if a name is already taken, and nothing if the page is already included.

An included page can't be registered on.

## Layout


```
┌───────────────────────────────┐
│ summary                       │
├────────────────────┬──────────┤
│                    │ errors   │
│ latency            ├──────────┤
│                    │ users    │
└────────────────────┴──────────┘
```

- `add()` gives a widget a full-width row of its own.
- `row()` puts widgets side by side, equally unless given `widths`. `widths=(2, 1)` gives the first two thirds.
- `column()` stacks widgets top to bottom, in one slot of a row.
- Rows show in the order they were made. On a narrow screen, row items wrap under each other.

`row()` and `column()` take new widgets, or ones already added, which move out of their old row:

```python
latency = page.add(TimeSeriesChart("latency"))
page.row(Number("users"), latency)
```

## Tabs

A page holds either widgets or tabs. Each tab is a page of its own, at `/<page>/<tab>`, listed in a sidebar. Visiting the page shows its first tab.

```python
from dachshund import BarChart, Page

page = Page("activity", title="Activity")

commands = page.tab("commands", title="Commands")
commands.add(BarChart("on_command", x="name"))

errors = page.tab("errors", title="Errors")
errors.add(BarChart("command_error", x="name"))
```

## Without a `Page`

Widgets can also go straight on the dashboard. Without `page=`, they land on the default page, "Overview" in the navigation.

```python
import dachshund
from dachshund import Number, TimeSeriesChart

latency = dachshund.add(TimeSeriesChart("latency"))
dachshund.add(Number("errors"), page="errors")

dachshund.page("errors", title="Errors")
```

`dachshund.row()` and `dachshund.column()` lay them out, with `page=` naming the row's page.

## Shipping a page

A library can ship a page for applications to include:

```python
# a package, dachshund_discord/__init__.py
from dachshund import Number, Page, Table


def discord_page(name: str = "discord") -> Page:
    page = Page(name, title="Discord")
    page.add(Number("guild_count"))
    page.add(Table("guilds", columns=["id", "name", "members"], key="id"))
    return page
```

```python
dachshund.include(discord_page())
```
