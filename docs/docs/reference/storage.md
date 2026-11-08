# Storage

`Storage` is where persisted widget state is saved. A dashboard has none until you give it one, see [Persistent Storage](../guides/persistent-storage.md).

```python
import dachshund
from dachshund.storage import SQLiteStorage

dachshund.init("Ada", storage=SQLiteStorage("widget_state.db"))
```

::: dachshund.storage.protocol.Storage

::: dachshund.storage.sqlite.SQLiteStorage

::: dachshund.storage.protocol.SyncStorage
