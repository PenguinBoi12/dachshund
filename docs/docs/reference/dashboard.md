# Dashboard

`Dashboard` holds everything one process shows on its dashboard. Most applications use the module-level functions below, which work on a default dashboard started by `dachshund.init()`.

```python
import dachshund
from dachshund import TimeSeriesChart

dachshund.init("Ada", description="Code Society's Matrix bot")
dachshund.row(TimeSeriesChart("latency"))
dachshund.emit("latency", value=96)
```

::: dachshund.registry
    options:
      members:
        - Dashboard
        - default
        - init
        - shutdown
        - include
        - action
        - emit
        - page
        - row
        - column
