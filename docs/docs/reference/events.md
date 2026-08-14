# Events

`Event` is a single thing that happened: a source name, the fields it carried, and when it happened. `dachshund.emit()` builds one from whatever you pass it, and widgets read it back through `render` and `update`.

```python
from dachshund import Event

Event("latency", {"value": 96})
```

::: dachshund.storage.events.Event
