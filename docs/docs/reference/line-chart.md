# Line Chart

`LineChart` draws one field of its events against another.

```python
import dachshund
from dachshund import LineChart

with dachshund.row():
    dachshund.add(LineChart("throughput", x="requests", y="latency"))
dachshund.emit("throughput", requests=120, latency=96)
```

::: dachshund.widgets.chart.line.LineChart
