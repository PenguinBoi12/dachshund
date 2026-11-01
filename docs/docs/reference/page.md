# Page

`Page` holds widgets, their layout and their actions, and goes on the dashboard with `dachshund.include()`. See the [Pages](../guides/pages.md) guide.

```python
import dachshund
from dachshund import Number, Page, TimeSeriesChart

page = Page("overview", title="Overview")

page.row(
    TimeSeriesChart("latency"),
    page.column(Number("errors"), Number("users")),
    widths=(2, 1),
)

dachshund.include(page)
```

::: dachshund.layout.Page

::: dachshund.layout.Column

::: dachshund.layout.Row
