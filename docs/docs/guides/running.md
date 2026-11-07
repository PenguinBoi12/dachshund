# Running with Your App

Dachshund runs inside your application's process. Call `dachshund.init()` once, where your application starts, and `dachshund.shutdown()` where it stops. Pages can be included before or after `init()`.

## Options

```python
dachshund.init(
    "My service",
    description="What my service does",
    host="127.0.0.1",
    port=1212,
    path="dachshund.db",
    storage=None,
    context={},
    authorize=None,
    login_url=None,
    timezone="UTC",
)
```

| Option | What it sets |
|---|---|
| `name`, `description` | The title and subtitle at the top of every page. |
| `host`, `port` | Where the dashboard listens. Defaults to `127.0.0.1:1212`. |
| `path` | The SQLite file events are kept in. `":memory:"` keeps them out of any file. |
| `storage` | Where persisted widget state is saved, see [Persistent Storage](persistent-storage.md). |
| `context` | Passed as `ctx` to every action and table loader, see [Actions](actions.md#context). |
| `authorize`, `login_url` | Who may see each page and run each action, see [Authentication](authentication.md). |
| `timezone` | Where `"day"`, `"week"` and `"month"` windows and daily buckets start, see [Aggregating](widgets.md#aggregating). Defaults to `"UTC"`. |

`path` and `storage` only apply to the first call that touches the dashboard. Call `init()` before adding widgets or including pages so they're used.

## A script

The dashboard runs on a background thread that ends with the process. A script has to keep running for the dashboard to stay up.

```python
import time

import dachshund

dachshund.init("My script")
dachshund.include(overview_page)

while True:
    dachshund.emit("queue_size", value=queue.size())
    time.sleep(1)
```

## FastAPI

Start it in the app's lifespan:

```python
from contextlib import asynccontextmanager

import dachshund
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    dachshund.init("My API")
    dachshund.include(overview_page)
    yield
    dachshund.shutdown()


app = FastAPI(lifespan=lifespan)
```

`init()` runs inside the app's event loop here, so async actions run on that loop too.

## Flask

Start it in the application factory:

```python
import dachshund
from flask import Flask


def create_app() -> Flask:
    app = Flask(__name__)

    dachshund.init("My app")
    dachshund.include(overview_page)

    return app
```

## An asyncio application

Call `init()` from inside the running loop, so async actions run on it and can await your application's clients:

```python
import asyncio

import dachshund


async def main() -> None:
    dachshund.init("My service")
    dachshund.include(overview_page)

    await serve_forever()


asyncio.run(main())
```

## Several workers

Under a server running several worker processes, such as gunicorn or uvicorn with `--workers`, every worker calls `init()`, but only one can hold the dashboard's port. The others stand by and take over if it stops.

Every worker writes its events to the same events file, so a page shows all of them when it loads. Live updates only come from the worker serving the dashboard, so events from the others show on the next page load. Persisted widget state isn't merged between workers.

## Exposing the dashboard

!!! danger
    The dashboard has no authentication by default. Anyone who can reach its port sees every page and can run every action. Keep it on `127.0.0.1`, or give it an `authorize` function, see [Authentication](authentication.md).

To listen on every interface, for example inside a container:

```python
dachshund.init("My service", host="0.0.0.0", port=1212)
```

A reverse proxy must allow WebSocket upgrades on `/_ws`, which carries the live updates.
