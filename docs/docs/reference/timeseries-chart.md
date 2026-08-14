# Time Series Chart

`TimeSeriesChart` draws a line over time, a point per event. There is no `x` to give: a point sits where its event happened, read from `y`.

```python
import dachshund

dachshund.chart("latency", type="timeseries")
dachshund.emit("latency", value=96)
```

::: dachshund.widgets.chart.timeseries.TimeSeriesChart
