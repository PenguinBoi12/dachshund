# Number

`Number` shows the latest number from its source, big. `unit` names what it's measured in, shown next to the number.

```python
import dachshund

dachshund.widget("cpu", type="number", title="CPU Load", unit="%")
dachshund.emit("cpu", value=42)
```

::: dachshund.widgets.number.number.Number
