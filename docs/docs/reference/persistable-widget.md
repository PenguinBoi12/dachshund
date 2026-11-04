# Persistable Widget

`PersistableWidget` is the base class of a widget whose state can be kept across restarts, see [Persistent Storage](../guides/persistent-storage.md).

```python
import dachshund
from dachshund import Number

with dachshund.row():
    dachshund.add(Number("cpu", persist=True))
```

::: dachshund.widgets.persistable.PersistableWidget
