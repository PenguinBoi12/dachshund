# Pages

A dashboard is split into pages, each at its own URL and in the navigation. A [Page](../reference/page.md) holds widgets, their layout and actions.

```python
import dachshund
from dachshund import Number, Page, Text, TimeSeriesChart

overview_page = Page("overview", title="Overview")

overview_page.add(Text("summary"))
overview_page.row(
    TimeSeriesChart("latency"),
    overview_page.column(Number("errors"), Number("users")),
    widths=(2, 1),
)


@overview_page.action("flush", label="Flush cache")
def flush(ctx) -> None:
    ctx["cache"].clear()


dachshund.include(overview_page)
dachshund.init("My service", context={"cache": cache})
```

Pages show in the navigation in the order they're included. Widget and action names are unique across the dashboard, and `include()` adds nothing if one is already taken.

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

`row()` and `column()` also take widgets already added, which move out of their old row:

```python
latency = overview_page.add(TimeSeriesChart("latency"))
overview_page.row(Number("users"), latency)
```

## Tabs

A page holds either widgets or tabs. Each tab is a page of its own, at `/<page>/<tab>`, listed in a sidebar. Visiting the page shows its first tab.

```python
from dachshund import BarChart, Page

activity_page = Page("activity", title="Activity")

commands = activity_page.tab("commands", title="Commands")
commands.add(BarChart("commands", x="name"))

errors = activity_page.tab("errors", title="Errors")
errors.add(BarChart("errors_per_command", x="name"))
```

## Without a `Page`

Widgets can also go straight on the dashboard. Without `page=`, they land on the default page, "Overview" in the navigation.

```python
import dachshund
from dachshund import Number, TimeSeriesChart

dachshund.add(TimeSeriesChart("latency"))
dachshund.add(Number("errors"), page="errors")
```

`dachshund.row()` and `dachshund.column()` lay them out, with `page=` naming the row's page.

As a dashboard grows, see [Bigger Dashboard](bigger-dashboard.md) for how to split it across modules.
