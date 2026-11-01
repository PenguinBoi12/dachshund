# Persistent Storage

A widget built with `persist=True` keeps its state across restarts. That state is saved to the dashboard's `storage`, which this guide sets up. For the widget side, see [Persisting](custom-widgets.md#persisting).

## SQLiteStorage

The built-in backend, in a SQLite file of its own:

```python
import dachshund
from dachshund.storage.sqlite import SQLiteStorage

dachshund.init("Ada", storage=SQLiteStorage("widget_state.db"))
```

A dashboard has no storage by default. Adding a widget with `persist=True` to one raises an error.

## Writing your own

A backend is any class with these two methods:

```python
async def save(self, key: str, value: dict) -> None: ...
async def load(self, key: str) -> dict | None: ...
```

`save` replaces the value under `key`, and `load` returns it, or `None` for an unknown key.

A backend on a synchronous client, such as an ORM, subclasses [SyncStorage][dachshund.storage.protocol.SyncStorage] and writes `_save` and `_load` as plain methods. Each call runs in a thread, so the client must be safe to call from any thread.

```python
import json

from sqlmodel import Field, Session, SQLModel, create_engine
from dachshund.storage.protocol import SyncStorage


class WidgetState(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str


class SQLModelStorage(SyncStorage):
    def __init__(self, url: str) -> None:
        self.engine = create_engine(url)
        SQLModel.metadata.create_all(self.engine)

    def _save(self, key: str, value: dict) -> None:
        with Session(self.engine) as session:
            existing = session.get(WidgetState, key)
            if existing is None:
                session.add(WidgetState(key=key, value=json.dumps(value)))
            else:
                existing.value = json.dumps(value)
                session.add(existing)
            session.commit()

    def _load(self, key: str) -> dict | None:
        with Session(self.engine) as session:
            row = session.get(WidgetState, key)
            return json.loads(row.value) if row else None
```

```python
dachshund.init("Ada", storage=SQLModelStorage("sqlite:///widget_state.db"))
```

## Raw events

The events feeding charts aren't saved to `storage`. They're kept in their own SQLite file, the dashboard's `path`, and trimmed over time.
