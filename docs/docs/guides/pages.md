# Pages & Layout

## Without a `Page`

The smallest dashboard puts widgets straight on it. They land on the default page, "Overview" in the navigation.

```python
import dachshund
from dachshund.widgets import Number, TimeSeriesChart

dachshund.init("My service")

with dachshund.row():
    dachshund.add(Number("users"))
    dachshund.add(TimeSeriesChart("latency"))
```

## Layout

Widgets live in rows, laid out with `with` blocks, so the indentation is the layout. `add()` puts a widget in the innermost open block.

| `add()` inside | the widget goes |
|---|---|
| a `column()` | in that column, under the widgets already there |
| a `row()` | in a column of its own, side by side with the others |
| neither | nowhere: it raises `ValueError` |

```python
with dachshund.row():
    dachshund.add(Text("summary"))

with dachshund.row():
    dachshund.add(TimeSeriesChart("latency"))
    with dachshund.column(span=4):
        dachshund.add(Number("errors"))
        dachshund.add(Number("users"))
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

- Every row is a 12-column grid. A column's `span` is its width out of 12: 6 is half, 4 a third, 3 a quarter.
- Columns without a span share what's left evenly, so `latency` above takes 8.
- A full-width widget is a row with one widget, like `summary`.
- Columns line up from one row to the next, since every row uses the same 12 columns.
- Rows show in the order they were opened. On a narrow screen, every column takes the full width.
- Loops work inside blocks:

```python
with dachshund.row():
    for name in ("cpu", "memory", "disk"):
        dachshund.add(Number(name))  # 4 + 4 + 4
```

To keep a reference to a widget, build it first, then place it:

```python
sessions = Table("sessions", columns=["user"], key="user")

with dachshund.row():
    dachshund.add(sessions)
```

## Pages

A [Page](../reference/page.md) groups widgets under its own URL and entry in the navigation. It's laid out the same way, through its own `row()`, `column()` and `add()`, then put on the dashboard with `include()`.

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

dachshund.include(overview_page)
```

Pages show in the navigation in the order they're included. Widget and action names are unique across the dashboard, and `include()` adds nothing if one is already taken.

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

As a dashboard grows, see [Bigger Dashboard](bigger-dashboard.md) for how to split it across modules.
