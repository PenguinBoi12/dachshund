# Number

`Number` shows the latest number of its source, big.

```python
import dachshund
from dachshund import Number

with dachshund.row():
    dachshund.add(Number("cpu", title="CPU Load", unit="%"))
dachshund.emit("cpu", value=42)
```

::: dachshund.widgets.number.number.Number
