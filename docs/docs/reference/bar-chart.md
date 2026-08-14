# Bar Chart

`BarChart` totals the events of its source into a bar per category. `x` names the field the categories come from and `y` what is totalled.

```python
import dachshund

dachshund.chart("commands", type="bar", x="name")
dachshund.emit("commands", name="/ban", value=1)
```

::: dachshund.widgets.chart.bar.BarChart
