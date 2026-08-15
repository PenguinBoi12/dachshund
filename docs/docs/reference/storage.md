# Storage

`Storage` is where a persisting widget's own state lives, a key to a JSON-shaped value, nothing more. There's no default: a dashboard only persists widget state when you configure one.

```python
import dachshund
from dachshund.storage.sqlite import SQLiteStorage

dachshund.init("Ada", storage=SQLiteStorage("widget_state.db"))
```

`SQLiteStorage` is the one built in, self-contained and separate from wherever raw events live. See the [Persistent Storage](../guides/persistent-storage.md) guide for setting it up and for writing your own backend.

::: dachshund.storage.protocol.Storage

::: dachshund.storage.sqlite.SQLiteStorage
