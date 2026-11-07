# Logs

`Logs` shows the application's Python logs live, newest first. See the [Logs](../guides/logs.md) guide.

```python
import dachshund
from dachshund.widgets import Logs

with dachshund.row():
    dachshund.add(Logs("api_errors", logger="myapp.api", level="ERROR"))
```

::: dachshund.widgets.logs.logs.Logs
