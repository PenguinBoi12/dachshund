# Logs

A [Logs](../reference/logs.md) widget shows your application's Python logs as they happen, newest first. Adding it is all the setup: it captures its logger.

```python
import logging

import dachshund
from dachshund.widgets import Logs

logging.basicConfig(level=logging.INFO)

with dachshund.row():
    dachshund.add(Logs("logs"))
```

Every line shows its time, level, logger and message. A line logged with an exception, like `logger.exception(...)`, expands to its traceback when clicked.

## Which lines

```python
with dachshund.row():
    dachshund.add(Logs("api_errors", logger="myapp.api", level="ERROR"))
```

- `logger` captures that logger and its children: `"myapp.api"` shows `myapp.api.users` too, but not `myapp.web`. Without it, every logger.
- `level` is the lowest level captured, `"INFO"` by default. Levels below it aren't stored, so the browser doesn't offer them: `Logs(level="DEBUG")` captures debug lines too.

A logger only passes the levels it's set to. The root logger passes `WARNING` and up until it's configured, so a `Logs` widget at `INFO` logs a warning when its logger would hide its lines. Set the level with `logging.basicConfig(level=logging.INFO)` or `logging.getLogger("myapp").setLevel(logging.INFO)`.

## In the browser

- A toggle per captured level shows or hides its lines, all on by default. Turn off `INFO` to see everything else, or leave only `ERROR` on.
- The search box matches the time, level, logger and message.
- Lines scroll inside a fixed-height card, newest first, 50 to a page.
- **Pause** stops new lines from moving the view and resetting the scroll while you read. **Resume** catches up.
- The pager moves through older lines.

## How long lines are kept

The newest `keep` lines, 500 by default, stay in the dashboard's events file, across restarts. No `storage` is needed.

```python
Logs("logs", keep=2000)
```

## loguru

loguru doesn't go through `logging` by default. Send its records there, and a `Logs` widget picks them up:

```python
import logging

from loguru import logger

logger.add(logging.getLogger("myapp").handle)
```
