# Time Series Chart

`TimeSeriesChart` draws a line over time, one point per event.

```python
import dachshund
from dachshund import TimeSeriesChart

dachshund.row(TimeSeriesChart("latency"))
dachshund.emit("latency", value=96)
```

::: dachshund.widgets.chart.timeseries.TimeSeriesChart
