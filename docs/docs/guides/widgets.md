# Choosing a Widget

| Widget | Shows | Fed by |
|---|---|---|
| [Number](../reference/number.md) | The latest number, big | `emit("cpu", value=42)` |
| [Text](../reference/text.md) | The latest markdown | `emit("notes", value="**Deployed** v1.2")` |
| [TimeSeriesChart](../reference/timeseries-chart.md) | A line over time | `emit("latency", value=96)` |
| [LineChart](../reference/line-chart.md) | One field against another | `emit("load", requests=120, latency=96)` |
| [BarChart](../reference/bar-chart.md) | A total per category | `emit("commands", name="/deploy", value=1)` |
| [Table](../reference/table.md) | One row per event or key | `emit("sessions", user="ada", ip="10.0.0.1")` |
| [Button](../reference/button.md) | Buttons running actions | Nothing, see [Actions](../reference/actions.md) |

For anything else, [write your own](custom-widgets.md).
