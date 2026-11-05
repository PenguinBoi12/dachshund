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
| [Number](../reference/number.md) | The latest number, big | `y`, `"value"` by default | `emit("cpu", value=42)` |
| [Text](../reference/text.md) | The latest markdown | `y`, `"value"` by default | `emit("notes", value="**Deployed** v1.2")` |
| [TimeSeriesChart](../reference/timeseries-chart.md) | A line over time | `y`, or one field per line | `emit("latency", value=96)` |
| [LineChart](../reference/line-chart.md) | One field against another | `x` and `y` | `emit("load", requests=120, latency=96)` |
| [BarChart](../reference/bar-chart.md) | A total per category | `x` for the category, `y` added to its total | `emit("commands", name="/deploy", value=1)` |
| [Table](../reference/table.md) | One row per event or key | the fields named in `columns` | `emit("sessions", user="ada", ip="10.0.0.1")` |
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

## How long events are kept

Each widget is built from the latest 500 events of its source. After 30 minutes, events are averaged into one point per minute for line and time series charts, and dropped for every other widget.

To keep a widget's state for good, like a running total or the last value, build it with `persist=True`. It needs the dashboard's `storage`, see [Persistent Storage](persistent-storage.md).
