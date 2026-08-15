# Persistent Storage

A widget can keep its own state across a restart (see [Persisting it](custom-widgets.md#persisting-it) in the Custom Widgets guide for the widget side of this). None of that is saved anywhere until a dashboard has somewhere to put it. This guide covers setting that up, and writing your own backend if the built-in one doesn't fit.

## The built-in backend

`SQLiteStorage` is the one dachshund ships. It's self-contained, give it a path and it owns its own file, separate from wherever raw events live:

```python
import dachshund
from dachshund.storage.sqlite import SQLiteStorage

dachshund.init("Ada", storage=SQLiteStorage("widget_state.db"))
```

Without `storage=`, nothing persists. Registering a widget with `persist=True` on a dashboard that has no storage configured raises an error immediately, rather than quietly doing nothing.

## Writing your own

`Storage` is a `Protocol`, so conformance is structural: a class with matching `save`/`load` methods works, no dachshund base class to import or subclass.

```python
async def save(self, key: str, value: dict) -> None: ...
async def load(self, key: str) -> dict | None: ...
```

`save` replaces whatever was under a key. `load` reads it back, or returns `None` if nothing's there yet. That's the whole contract, one key to one JSON-shaped value.

Here's one backed by [SQLModel](https://sqlmodel.tiangolo.com/), for a project that's already using it elsewhere:

```python
import asyncio
import json

from sqlmodel import Field, Session, SQLModel, create_engine


class WidgetState(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str


class SQLModelStorage:
    def __init__(self, url: str) -> None:
        self.engine = create_engine(url)
        SQLModel.metadata.create_all(self.engine)

    async def save(self, key: str, value: dict) -> None:
        await asyncio.to_thread(self._save, key, value)

    async def load(self, key: str) -> dict | None:
        return await asyncio.to_thread(self._load, key)

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

`Session` is synchronous, so `save`/`load` run it through `asyncio.to_thread` rather than blocking the event loop, the same reason `SQLiteStorage` runs its own connection through a dedicated executor. That threading choice is yours to make though, `Storage` doesn't require it; a backend built on an async driver (an async Postgres or Redis client, for instance) can just `await` directly.

## Why raw events aren't part of this

Events (what feeds charts like `TimeSeriesChart`) aren't backed by `Storage`, and can't be: they're an unbounded, ever-growing log with windowed queries (`WHERE source = ? ORDER BY at LIMIT ?`), while `Storage` is a single key replaced wholesale each time. Forcing an event log through `save`/`load` would mean loading the entire history and rewriting it on every single event, and `load` alone has no way to ask for "just the last 500." `Storage` is deliberately scoped to what a widget's own derived state actually needs, small, and replaced as a whole, not appended to forever.
