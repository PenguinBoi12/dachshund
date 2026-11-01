# Events

`Event` is one thing that happened: a source, its fields and when. `dachshund.emit()` builds one.

```python
import dachshund

dachshund.emit("latency", value=96)
```

::: dachshund.storage.events.Event
