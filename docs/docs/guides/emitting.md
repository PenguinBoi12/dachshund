# Emitting Events

Widgets are built from events. An event has a source name and fields, and every widget whose source matches shows it.

```python
import dachshund

dachshund.emit("latency", value=96)
dachshund.emit("commands", name="/deploy", value=1)
```

`emit()` returns right away and can be called from any thread or event loop, before or after `init()`.

## Sources

A widget's source is its name, unless it's given one:

```python
from dachshund.widgets import BarChart, Number

with dachshund.row():
    dachshund.add(Number("latency"))
with dachshund.row():
    dachshund.add(BarChart("slow_routes", source="latency", x="route"))

dachshund.emit("latency", route="/users", value=840)
```

Both widgets show that event. One source can feed any number of widgets.

## Fields

Each widget reads the fields it needs, the rest are ignored:

| Widget | Reads |
|---|---|
| `Number`, `Text` | `y`, `"value"` by default |
| `TimeSeriesChart` | `y`, or one field per line |
| `LineChart` | `x` and `y` |
| `BarChart` | `x` for the category, `y` added to its total |
| `Table` | the fields named in `columns` |

A number can be an `int`, a `float`, a numeric string, a `datetime` or a `timedelta`. A field that's missing or not a number leaves a gap, and logs a warning once.

## How long events are kept

Each widget is built from the latest 500 events of its source. After 30 minutes, events are averaged into one point per minute for line and time series charts, and dropped for every other widget.

To keep a widget's state for good, like a running total or the last value, build it with `persist=True`. See [Persistent Storage](persistent-storage.md).

```python
with dachshund.row():
    dachshund.add(BarChart("commands", x="name", persist=True))
```
