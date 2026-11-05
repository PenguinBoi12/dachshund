# Running with Your App

Dachshund runs inside your application's process. Call `dachshund.init()` once, where your application starts, and `dachshund.shutdown()` where it stops.

## A script

The dashboard runs on a background thread that ends with the process. A script has to keep running for the dashboard to stay up.

```python
import time

import dachshund

dachshund.include(overview_page)
dachshund.init("My script")

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
    dachshund.include(overview_page)
    dachshund.init("My API")
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

    dachshund.include(overview_page)
    dachshund.init("My app")

    return app
```

## An asyncio application

Call `init()` from inside the running loop, so async actions run on it and can await your application's clients:

```python
import asyncio

import dachshund


async def main() -> None:
    dachshund.include(overview_page)
    dachshund.init("My service")

    await serve_forever()


asyncio.run(main())
```

## Several workers

Under a server running several worker processes, such as gunicorn or uvicorn with `--workers`, every worker calls `init()`, but only one can hold the dashboard's port. The others stand by and take over if it stops.

Every worker writes its events to the same events file, so a page shows all of them when it loads. Live updates only come from the worker serving the dashboard, so events from the others show on the next page load. Persisted widget state isn't merged between workers.
