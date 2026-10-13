# Custom Widgets

A widget is a card on the dashboard, built from the events emitted under its source. The built-in charts are all widgets themselves: see [Time Series Chart](../reference/timeseries-chart.md), [Line Chart](../reference/line-chart.md), and [Bar Chart](../reference/bar-chart.md). This guide covers building your own by subclassing [Widget](../reference/widget.md).

## Start with the class

A widget needs a `type` of its own and an `op` telling the client how to apply an update:

- `op = "replace"` rebuilds the whole card on every event.
- `op = "append"` adds one point to what's already drawn.

Subclassing `Widget` registers it the moment the class is defined. There's no separate registration call.

```python
from dataclasses import KW_ONLY, dataclass
from pathlib import Path
from typing import ClassVar

from dachshund import Widget


@dataclass
class Gauge(Widget):
    _: KW_ONLY

    y: str = "value"

    type: ClassVar[str] = "gauge"
    op: ClassVar[str] = "replace"
    script: ClassVar[Path] = Path(__file__).parent / "gauge.js"
```

`_: KW_ONLY` makes every field declared after it keyword-only, matching how the built-in charts declare their own fields. `y` names the field this gauge reads, and `script` points at the JS file that draws it, covered next.

## render()

`render(events)` builds the whole card from every event kept for the widget's source. It runs when the page loads, and again whenever a `replace` widget needs rebuilding. `Widget.value(event, field)` reads a field as a number, or `None` if the event doesn't carry one or it isn't numeric.

```python
    def render(self, events):
        value = self.value(events[-1], self.y) if events else None
        return {"value": value}
```

`update(event)` builds a single incremental change, and only matters for `op = "append"` widgets. Gauge replaces the whole card, so it doesn't need one. Look at [LineChart][dachshund.LineChart]'s source for what an `append` widget's `update()` looks like.

## Persisting it

Right now Gauge only knows what `events` it's handed, which is the recent, windowed history. Nothing stops it from keeping its own state that survives a restart, the same way [BarChart][dachshund.BarChart]'s `persist` does. Three more hooks, all optional:

```python
    persist: bool = False

    last: float | None = field(default=None, init=False, repr=False, compare=False)

    def accumulate(self, event):
        if not self.persist:
            return
        value = self.value(event, self.y)
        if value is not None:
            self.last = value

    def snapshot(self):
        return {"last": self.last} if self.persist else None

    def restore(self, data):
        self.last = data.get("last")
```

`render()` reads `self.last` instead of `events` when persisting:

```python
    def render(self, events):
        value = self.last if self.persist else (self.value(events[-1], self.y) if events else None)
        return {"value": value}
```

This needs a `Storage` configured on the dashboard, the same as any persisting widget:

```python
from dachshund.storage.sqlite import SQLiteStorage

dachshund.init(storage=SQLiteStorage("widget_state.db"))
dachshund.widget("cpu", type="gauge", persist=True)
```

`accumulate`/`snapshot`/`restore` are plain `Widget` hooks; any widget, built-in or your own, can implement them the same way, as Gauge just did. That's the right choice when the state is a single value, like Gauge's `last`.

When it's naturally one entry per string key instead of a single value, subclass [KeyedWidget][dachshund.widgets.state.KeyedWidget] rather than writing the three hooks yourself; `Table` and `BarChart` both do.

## Using it

Once the module defining `Gauge` has been imported, it's usable like any built-in widget:

```python
import dachshund

dachshund.widget("cpu", type="gauge")
dachshund.emit("cpu", value=42)
```

## Drawing it in the browser

The Python side builds the payload. Drawing it is the client's job, and it lives in `gauge.js`, next to `gauge.py`. `script` points at it; dachshund serves it, at a URL derived from `type`, and loads it before `dashboard.js` runs.

A renderer registers itself with `window.Dachshund.widget(type, renderer)`, guaranteed to exist before any widget script runs. It needs `mount(card, payload)`, which draws the card the first time and returns whatever state it needs later, plus a `replace(state, payload)` or `append(state, point)` matching the widget's `op`:

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

Every card gets a `.card-content` div, whatever its type; it carries no styling beyond spacing, so a widget wanting a fixed size or its own layout adds that itself. `style: ClassVar[Path]` ships CSS the same way `script` ships JS:

```python
    style: ClassVar[Path] = Path(__file__).parent / "gauge.css"
```

The built-in chart types use this same mechanism, registered from `dachshund/widgets/chart/charts.js`, a good second example to read.
