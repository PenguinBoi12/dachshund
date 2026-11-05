# Testing

A `Page` is a plain object, so its widgets, rows and actions can be checked directly:

```python
from dachshund import Row

from myapp.dashboard.pages.overview import overview_page


def test_overview_page__expect_latency_beside_users():
    assert overview_page.rows[1] == Row(["latency", "users"], (2, 1))


def test_overview_page__expect_the_deactivate_action():
    assert "deactivate" in overview_page.actions
```

To check pages together, include them in a `Dashboard` of their own. `path=":memory:"` keeps its events out of any file:

```python
from dachshund import Dashboard

from myapp.dashboard.pages.activity import activity_page
from myapp.dashboard.pages.overview import overview_page


def test_dashboard__expect_every_page_included():
    dashboard = Dashboard(path=":memory:")

    dashboard.include(overview_page)
    dashboard.include(activity_page)

    assert list(dashboard.pages) == ["overview", "activity"]
```

A dashboard with persisted widgets also needs a `storage`, such as `SQLiteStorage(":memory:")`.

Actions and loaders are plain functions, called with whatever `ctx` the test needs:

```python
from dachshund.widgets import TableQuery

from myapp.dashboard.loaders import load_users


async def test_load_users__expect_a_first_page():
    rows, total = await load_users({"db": FakeDatabase()}, TableQuery(limit=5))

    assert len(rows) == 5
```
