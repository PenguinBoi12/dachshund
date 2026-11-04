# Time Series Chart

`TimeSeriesChart` draws a line over time, one point per event.

```python
import dachshund
from dachshund import TimeSeriesChart

with dachshund.row():
    dachshund.add(TimeSeriesChart("latency"))
dachshund.emit("latency", value=96)
```

::: dachshund.widgets.chart.timeseries.TimeSeriesChart
