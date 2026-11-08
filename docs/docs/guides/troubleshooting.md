# Troubleshooting

## The dashboard doesn't load

- **The process exited.** The dashboard runs on a background thread and stops with the process. See [A script](running.md#a-script).
- **The port is taken.** When another process holds the port, the dashboard logs a critical message and retries in the background until the port is free. Pass another `port` to `init()`, or stop the other process.
- **It's on another interface.** By default the dashboard only listens on `127.0.0.1`. To reach it from another machine or a container, see [Exposing the dashboard](running.md#exposing-the-dashboard).

## The dashboard keeps asking to log in

- **`authorize` returns a falsy value.** Check what it receives: `request.headers` and `request.cookies`.
- **`authorize` raises.** The request is denied and the error logged, look for "authorize() failed".
- **The cookie doesn't reach the dashboard.** A cookie set on another host, or another subdomain without a covering `Domain`, isn't sent to it. See [Logging in](authentication.md#logging-in).

## A card stays empty

- **Nothing was emitted yet.** A card fills in with the first event of its source.
- **The source doesn't match.** A widget shows the events emitted under its name, or its `source`.
- **The field doesn't match.** `Number` reads `value` unless given another `y`. A missing or non-numeric field logs a warning once, see [Choosing a widget](widgets.md#choosing-a-widget).
- **The events are older than 30 minutes.** Only line and time series charts keep older events. Build the widget with `persist=True` to keep its state, see [How long events are kept](widgets.md#how-long-events-are-kept).

## A count over the last hour doesn't go down

An aggregate is refreshed with each event of its source and on page load, not on a timer. With no new event, it shows its value as of the last one. Reload the page to see it as of now.

## "wants to persist, but no storage is configured"

A widget built with `persist=True` needs the dashboard's `storage`. Pass it to `init()`, called before the widget is added or its page included:

```python
from dachshund.storage import SQLiteStorage

dachshund.init("My service", storage=SQLiteStorage("widget_state.db"))
```

## "already exists" or "already taken"

Widget and action names are unique across the whole dashboard, every page included. Rename one of the two.

## An action fails

- **A required argument is missing.** On a card, give it in `action_args`. On a table row, emit it as a field of the row.
- **An async action fails on another event loop.** Call `init()` from inside your application's running loop, so actions run on it. See [Running with Your App](running.md#an-asyncio-application).

## Some events only show after a reload

Under several worker processes, live updates only come from the worker serving the dashboard. Events from the other workers show on the next page load. See [Several workers](running.md#several-workers).
