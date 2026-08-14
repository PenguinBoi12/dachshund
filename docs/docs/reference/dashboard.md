# Dashboard

`Dashboard` is everything one process puts on its dashboard: it holds the widgets registered on it, buffers the events emitted to it, and owns the runtime that serves it. Most applications never build one directly; the module-level functions below work against a default dashboard that `dachshund.init()` starts.

```python
import dachshund

dachshund.init("Ada", description="Code Society's Matrix bot")
dachshund.chart("latency", type="timeseries")
dachshund.emit("latency", value=96)
```

::: dachshund.registry
    options:
      members:
        - Dashboard
        - default
        - init
        - shutdown
        - chart
        - widget
        - emit
