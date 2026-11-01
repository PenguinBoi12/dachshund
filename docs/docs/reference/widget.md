# Widget

`Widget` is the base class of every card. Subclass it to write your own, see [Custom Widgets](../guides/custom-widgets.md).

```python
from typing import ClassVar

from dachshund import Widget

class Gauge(Widget):
    type: ClassVar[str] = "gauge"

    def render(self, events):
        return {"value": self.value(events[-1], "value") if events else None}
```

::: dachshund.widgets.base.Widget
