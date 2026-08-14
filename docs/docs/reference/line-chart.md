# Line Chart

`LineChart` draws one value against another, both read from the event. `x` places a point along the axis and `y` is the field drawn.

```python
import dachshund

dachshund.chart("throughput", type="line", x="requests", y="latency")
dachshund.emit("throughput", requests=120, latency=96)
```

::: dachshund.widgets.chart.line.LineChart
