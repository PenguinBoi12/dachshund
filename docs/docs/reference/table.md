# Table

`Table` shows one row per kept event, with server-side pagination and a button per row for each of its actions.

```python
import dachshund
from dachshund import Table

with dachshund.row():
    dachshund.add(Table("sessions", columns=["user", "ip"], key="user"))
dachshund.emit("sessions", user="ada", ip="10.0.0.1")
```

::: dachshund.widgets.table.table.Table

::: dachshund.widgets.query.TableQuery
