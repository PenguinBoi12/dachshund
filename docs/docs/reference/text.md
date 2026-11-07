# Text

`Text` shows the latest markdown of its source.

```python
import dachshund
from dachshund.widgets import Text

with dachshund.row():
    dachshund.add(Text("changelog", title="Release Notes"))
dachshund.emit("changelog", value="**v1.2** fixed the thing.")
```

::: dachshund.widgets.text.text.Text
