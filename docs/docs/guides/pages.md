# Pages

A dashboard is split into pages, each at its own URL and in the navigation. A [Page](../reference/page.md) holds widgets, their layout and actions.

```python
import dachshund
from dachshund import Page
from dachshund.widgets import Number, Text, TimeSeriesChart

overview_page = Page("overview", title="Overview")

with overview_page.row():
    overview_page.add(Text("summary"))

with overview_page.row():
    overview_page.add(TimeSeriesChart("latency"))
    with overview_page.column(span=4):
        overview_page.add(Number("errors"))
        overview_page.add(Number("users"))


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

A page is rows on a 12-column grid, laid out with `with` blocks, so the indentation is the layout. Widgets live in rows: `add()` puts a widget in the innermost open block.

| `add()` inside | the widget goes |
|---|---|
| a `column()` | in that column, under the widgets already there |
| a `row()` | in a column of its own, side by side with the others |
| neither | nowhere: it raises `ValueError` |

A full-width widget is a row with one widget, like `summary` above.

- A column's `span` is its width out of 12: 6 is half, 4 a third, 3 a quarter. Columns without a span share what's left evenly, so `latency` above takes 8.
- Columns line up from one row to the next, since every row uses the same 12 columns.
- Rows show in the order they were opened. On a narrow screen, every column takes the full width.
- Loops work inside blocks:

```python
with overview_page.row():
    for name in ("cpu", "memory", "disk"):
        overview_page.add(Number(name))  # 4 + 4 + 4
```

This is the same model as LiveDashboard's `<.row>` / `<:col>`.

To keep a reference to a widget, build it first, then place it:

```python
sessions = Table("sessions", columns=["user"], key="user", persist=True)
with overview_page.row():
    overview_page.add(sessions)
```

## Tabs

A page holds either widgets or tabs. Each tab is a page of its own, at `/<page>/<tab>`, listed in a sidebar. Visiting the page shows its first tab.

```python
from dachshund import Page
from dachshund.widgets import BarChart

activity_page = Page("activity", title="Activity")

with activity_page.tab("commands", title="Commands"):
    with activity_page.row():
        activity_page.add(BarChart("commands", x="name"))

with activity_page.tab("errors", title="Errors"):
    with activity_page.row():
        activity_page.add(BarChart("errors_per_command", x="name"))
```

## Without a `Page`

Widgets can also go straight on the dashboard. Without `page=`, they land on the default page, "Overview" in the navigation.

```python
import dachshund
from dachshund.widgets import Number, TimeSeriesChart

with dachshund.row():
    dachshund.add(TimeSeriesChart("latency"))
with dachshund.row(page="errors"):
    dachshund.add(Number("errors"), page="errors")
```

`dachshund.row()` and `dachshund.column()` work like a page's. With `page=`, pass it to the `row()` and to each `add()` inside it.

As a dashboard grows, see [Bigger Dashboard](bigger-dashboard.md) for how to split it across modules.
