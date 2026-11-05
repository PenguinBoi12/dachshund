# Custom Widgets

A widget is a Python class building a payload from events, and a JavaScript renderer drawing it. Every built-in widget is made this way. This guide builds a gauge.

#### 1- Write the class

Subclass [Widget](../reference/widget.md) with a `type` of its own. The class is registered when it's defined.

```python
# gauge.py
from dataclasses import KW_ONLY, dataclass
from pathlib import Path
from typing import ClassVar

from dachshund.widgets import Widget


@dataclass
class Gauge(Widget):
    _: KW_ONLY

    y: str = "value"

    type: ClassVar[str] = "gauge"
    op: ClassVar[str] = "replace"
    script: ClassVar[Path] = Path(__file__).parent / "gauge.js"
```

- `op = "replace"` redraws the card on every event.
- `op = "append"` adds one point per event, through `update(event)`. See [LineChart][dachshund.widgets.LineChart] for an example.

#### 2- Build the payload

`render(events)` gets every kept event of the widget's source and returns what the renderer draws. `self.value(event, field)` reads a field as a number, `None` when missing or not numeric.

```python
    def render(self, events):
        return {"value": self.value(events[-1], self.y) if events else None}
```

#### 3- Draw it in the browser

`script` is served with the page. It registers a renderer under the widget's `type`, with `mount(card, payload)` for the first draw and `replace(state, payload)` or `append(state, point)` to match `op`.

```js
// gauge.js
(() => {
  "use strict";

  window.Dachshund.widget("gauge", {
    mount(card, payload) {
      const container = card.querySelector(".card-content");
      container.textContent = payload.value ?? "-";
      return { container };
    },
    replace(state, payload) {
      state.container.textContent = payload.value ?? "-";
    },
  });
})();
```

`mount` returns whatever state the later calls need. A `style` class attribute ships a stylesheet the same way:

```python
    style: ClassVar[Path] = Path(__file__).parent / "gauge.css"
```

#### 4- Add it

```python
import dachshund
from gauge import Gauge

with dachshund.row():
    dachshund.add(Gauge("cpu"))
dachshund.emit("cpu", value=42)
```

The built-in charts, in `dachshund/widgets/chart/`, make a good second example.

## Persisting

To keep a widget's state across restarts, subclass [PersistableWidget][dachshund.widgets.PersistableWidget] and write its three hooks. They're only called on a widget built with `persist=True`.

```python
from dataclasses import field

from dachshund.widgets import PersistableWidget


@dataclass
class Gauge(PersistableWidget):
    ...

    last: float | None = field(default=None, init=False, repr=False, compare=False)

    def accumulate(self, event):
        value = self.value(event, self.y)
        if value is not None:
            self.last = value

    def snapshot(self):
        return {"last": self.last}

    def restore(self, data):
        self.last = data.get("last")

    def render(self, events):
        if self.persist:
            return {"value": self.last}
        return {"value": self.value(events[-1], self.y) if events else None}
```

The dashboard needs a `storage`, see [Persistent Storage](persistent-storage.md):

```python
from dachshund.storage import SQLiteStorage

dachshund.init(storage=SQLiteStorage("widget_state.db"))
with dachshund.row():
    dachshund.add(Gauge("cpu", persist=True))
```

For state with one entry per key, subclass [KeyedWidget][dachshund.widgets.state.KeyedWidget] instead. It provides the three hooks.
