# Keyed Widget

`KeyedWidget` is the base class of a widget whose state is one entry per key, like `Table` and `BarChart`.

```python
from dachshund.widgets import KeyedWidget


class Leaderboard(KeyedWidget):
    type = "leaderboard"

    def accumulate(self, event):
        self.state.upsert(event.payload["user"], event.payload["score"])
```

::: dachshund.widgets.state.KeyedWidget
