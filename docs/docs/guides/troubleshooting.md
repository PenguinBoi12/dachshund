# Troubleshooting

## The dashboard doesn't load

- **The process exited.** The dashboard runs on a background thread and stops with the process. See [A script](running.md#a-script).
- **The port is taken.** When another process holds the port, the dashboard logs a critical message and retries in the background until the port is free. Pass another `port` to `init()`, or stop the other process.
- **It's on another interface.** By default the dashboard only listens on `127.0.0.1`. To reach it from another machine or a container, see [exposing the dashboard](../index.md#extra-exposing-the-dashboard).

## A card shows "—"

- **Nothing was emitted yet.** A card fills in with the first event of its source.
- **The source doesn't match.** A widget shows the events emitted under its name, or its `source`.
- **The field doesn't match.** `Number` reads `value` unless given another `y`. A missing or non-numeric field logs a warning once, see [Fields](emitting.md#fields).
- **The events are older than 30 minutes.** Only line and time series charts keep older events. Build the widget with `persist=True` to keep its state, see [How long events are kept](emitting.md#how-long-events-are-kept).

## "wants to persist, but no storage is configured"

A widget built with `persist=True` needs the dashboard's `storage`. Pass one before the widget is added:

```python
from dachshund.storage import SQLiteStorage

dachshund.default(storage=SQLiteStorage("widget_state.db"))
```

## "already exists" or "already taken"

Widget and action names are unique across the whole dashboard, every page included. Rename one of the two.

## An action fails

- **A required argument is missing.** On a card, give it in `action_args`. On a table row, emit it as a field of the row.
- **An async action fails on another event loop.** Call `init()` from inside your application's running loop, so actions run on it. See [Running with Your App](running.md#an-asyncio-application).

## Some events only show after a reload

Under several worker processes, live updates only come from the worker serving the dashboard. Events from the other workers show on the next page load. See [Several workers](running.md#several-workers).
