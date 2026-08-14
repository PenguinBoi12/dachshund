# Widget

`Widget` is the base class every card on the dashboard is built from. It turns the events kept for its source into whatever its renderer draws: `render` builds the whole card from every kept event, `update` builds a single incremental change, and the `type`/`op` class variables tell the client how to draw and apply it.

A custom widget needs nothing beyond a `type` of its own: subclassing `Widget` registers it the moment the class is defined, the same way the built-in chart types do.

```python
from dataclasses import ClassVar
from dachshund import Widget

class Gauge(Widget):
    type: ClassVar[str] = "gauge"
    op: ClassVar[str] = "replace"

    def render(self, events):
        ...

    def update(self, event):
        ...

# dachshund.widget("cpu", type="gauge") now builds one.
```

::: dachshund.widgets.base.Widget
