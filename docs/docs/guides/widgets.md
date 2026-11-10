# Widgets & Events

Widgets are built from events. An event has a source name and fields, and every widget whose source matches shows it.

```python
import dachshund

dachshund.emit("latency", value=96)
dachshund.emit("commands", name="/deploy", value=1)
```

`emit()` returns right away and can be called from any thread or event loop, before or after `init()`. Emit from wherever the event happens in your code.

## Choosing a widget

| Widget | Shows | Reads | Fed by |
|---|---|---|---|
| [Number](../reference/number.md) | The latest number, or an [aggregate](#aggregating), big | `y`, `"value"` by default | `emit("cpu", value=42)` |
| [Text](../reference/text.md) | The latest markdown | `y`, `"value"` by default | `emit("notes", value="**Deployed** v1.2")` |
| [TimeSeriesChart](../reference/timeseries-chart.md) | A line over time, a point per event or per [bucket](#aggregating) | `y`, or one field per line | `emit("latency", value=96)` |
| [LineChart](../reference/line-chart.md) | One field against another | `x` and `y` | `emit("load", requests=120, latency=96)` |
| [BarChart](../reference/bar-chart.md) | A total, or another [aggregate](#aggregating), per category | `x` for the category, `y` aggregated | `emit("commands", name="/deploy", value=1)` |
| [Table](../reference/table.md) | One row per event or key | the fields named in `columns` | `emit("sessions", user="ada", ip="10.0.0.1")` |
| [Logs](../reference/logs.md) | Python log lines, newest first | its `include` loggers, from `logging` | `logging.getLogger("myapp").info("started")`, see [Logs](logs.md) |
| [Button](../reference/button.md) | Buttons running actions | nothing | see [Actions](actions.md) |

Fields a widget doesn't read are ignored. A number can be an `int`, a `float`, a numeric string, a `datetime` or a `timedelta`. A field that's missing or not a number leaves a gap, and logs a warning once.

For anything else, [write your own](custom-widgets.md).

## Sources

A widget's source is its name, unless it's given one:

```python
from dachshund.widgets import BarChart, Number

with dachshund.row():
    dachshund.add(Number("latency"))
    dachshund.add(BarChart("slow_routes", source="latency", x="route"))

dachshund.emit("latency", route="/users", value=840)
```

Both widgets show that event. One source can feed any number of widgets.

## Aggregating

Instead of the latest value, `Number`, `TimeSeriesChart` and `BarChart` can show an aggregate of their source: how many events, or the total, average, min, max or number of distinct values of a field. Emit one event per thing that happens, and let the widget do the math:

```python
from datetime import timedelta

from dachshund.widgets import BarChart, Number, TimeSeriesChart

dachshund.init("My service", timezone="America/Toronto")

with dachshund.row():
    dachshund.add(Number("requests", aggregate="count", over=timedelta(hours=1)))
    dachshund.add(
        Number("requests", y="ms", aggregate="average", over=timedelta(minutes=5))
    )
    dachshund.add(Number("requests", y="user", aggregate="distinct", over="day"))

with dachshund.row():
    dachshund.add(
        TimeSeriesChart("requests", aggregate="count", every=timedelta(minutes=1))
    )
    dachshund.add(BarChart("requests", x="route", aggregate="count"))

dachshund.emit("requests", route="/users", ms=12, user="ada")
```

| `aggregate` | Shows |
|---|---|
| `"last"` | the latest value of `y`, `Number`'s default |
| `"count"` | how many events, whatever their fields |
| `"sum"` | the total of `y`, `BarChart`'s default |
| `"average"` | the average of `y` |
| `"min"`, `"max"` | the smallest and largest `y` |
| `"distinct"` | how many different values of `y` |

- `over` is how far back from now to look: a `timedelta`, or the current `"day"`, `"week"` or `"month"`. Without it, everything stored.
- `every` splits a `TimeSeriesChart` into one point per bucket of that length, a whole number of minutes. Without `over`, the chart shows the latest 500 buckets.
- `"day"`, `"week"`, `"month"` and daily buckets start at midnight in the dashboard's `timezone`, `"UTC"` by default.
- A `BarChart` aggregates per category, over its kept events, or all of them with `persist=True`. It has no `over`.

An aggregate is refreshed with each event of its source and on page load. A count over the last hour doesn't go down between events.

## Expanding a widget

Every card has an expand button in its corner, shown on hover. It opens the widget over the whole window, above a dimmed dashboard: charts redraw at the new size, and tables show 50 rows a page. Esc or the button closes it.

The open widget is in the page's URL as `?view=<name>`, so a link opens straight on it:

```
/activity?view=logs
```

## How long events are kept

Each widget is built from the latest 500 events of its source. After 30 minutes, events are rolled up into one bucket per minute, kept for good, holding how many events it saw and the count, sum, min and max of each numeric field. Line and time series charts draw a bucket as one averaged point. Each source's newest event always stays as it was emitted, and a [Logs](logs.md) widget's source keeps its newest `keep` lines.

Aggregates read those buckets, so they're exact for the last 30 minutes and accurate to the minute before that. Distinct values are only kept for the fields a `"distinct"` widget reads.

To keep other widgets' state for good, like a table's rows, build them with `persist=True`. It needs the dashboard's `storage`, see [Persistent Storage](persistent-storage.md).
