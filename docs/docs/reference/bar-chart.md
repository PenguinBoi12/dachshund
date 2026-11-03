# Bar Chart

`BarChart` totals a field of its events into one bar per category.

```python
import dachshund
from dachshund import BarChart

dachshund.row(BarChart("commands", x="name"))
dachshund.emit("commands", name="/ban", value=1)
```

::: dachshund.widgets.chart.bar.BarChart
