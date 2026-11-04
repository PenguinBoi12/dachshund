# Page

`Page` holds widgets, their layout and their actions, and goes on the dashboard with `dachshund.include()`. See the [Pages](../guides/pages.md) guide.

```python
import dachshund
from dachshund import Number, Page, TimeSeriesChart

page = Page("overview", title="Overview")

with page.row():
    with page.column(span=4):
        page.add(Number("errors"))
        page.add(Number("users"))
    page.add(TimeSeriesChart("latency"))

dachshund.include(page)
```

::: dachshund.layout.Page

::: dachshund.layout.Row

::: dachshund.layout.Column
