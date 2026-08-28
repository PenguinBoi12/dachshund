# Keyed Widget

`KeyedWidget` is the base for a widget whose persisted state is one entry per string key, a row, a category, a count per user. `Table` and `BarChart` are both built on it. Subclassing it gives you `persist`, `state`, `snapshot`, `restore`, and `sweep`; only `accumulate()` and `render()` are still yours to write, reading and writing `self.state.entries`.

```python
from dachshund.widgets.state import KeyedWidget

class Leaderboard(KeyedWidget):
    type = "leaderboard"

    def accumulate(self, event):
        if self.persist:
            self.state.upsert(event.payload["user"], event.payload["score"])
```

A widget whose state isn't naturally keyed by string, a single value rather than a dict of entries, implements `accumulate`/`snapshot`/`restore` on [Widget][dachshund.Widget] directly instead. See the [Custom Widgets](../guides/custom-widgets.md) guide.

::: dachshund.widgets.state.KeyedWidget
