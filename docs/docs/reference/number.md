# Number

`Number` shows one number of its source, big: the latest, or an aggregate over a window, see [Aggregating](../guides/widgets.md#aggregating).

```python
import dachshund
from dachshund.widgets import Number

with dachshund.row():
    dachshund.add(Number("cpu", title="CPU Load", unit="%"))

dachshund.emit("cpu", value=42)
```

::: dachshund.widgets.number.number.Number
