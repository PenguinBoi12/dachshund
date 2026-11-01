# Pages

A dashboard is split into pages, each at its own URL and in the navigation. A [Page](../reference/page.md) holds widgets, their layout and actions, and goes on the dashboard with `include()`.

```python
# myapp/dashboard/overview.py
from dachshund import Number, Page, Text, TimeSeriesChart

page = Page("overview", title="Overview")

summary = page.add(Text("summary"))
latency = page.add(TimeSeriesChart("latency", y=["check", "command"]))
errors = page.add(Number("errors"))
users = page.add(Number("users"))

page.row(summary)
page.row(latency, page.column(errors, users))


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

```python
page.row(summary)
page.row(latency, page.column(errors, users), widths=(2, 1))
```

```
┌───────────────────────────────┐
│ summary                       │
├────────────────────┬──────────┤
│                    │ errors   │
│ latency            ├──────────┤
│                    │ users    │
└────────────────────┴──────────┘
```

- A `row()` splits its width equally between its items. `widths=(2, 1)` gives the first two thirds.
- A `column()` stacks widgets top to bottom, in one slot of a row.
- Widgets in no row fill a grid of equal cards below the rows. A lone card spans the full width.
- On a narrow screen, row items wrap under each other.

`row()` and `column()` take the widgets `add()` returned, or their names.

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
