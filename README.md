# Dachshund
> *A live admin dashboard for any Python service, embedded in the process itself.*

> **Beta.** Dachshund works, but its API may still change between releases. Pin a version before depending on it.

## What is Dachshund
Dachshund runs as a thread inside your FastAPI app, Flask app, Discord bot, worker or daemon. There's no router to hook into and no extra service to deploy. Declare pages and widgets in code, emit events from anywhere, and the dashboard updates live over WebSocket.

#### Key features
- **Embedded**: starts with your process, nothing else to run
- **Live**: every `emit()` reaches the open pages as it happens
- **Pages**: group widgets into pages and tabs, lay them out in rows and columns
- **Actions**: buttons that call your own Python functions
- **Extensible**: write your own widgets in a few lines of Python and JavaScript

## Getting Started
#### 1- Install the package
**Requirements:** Python 3.10 or higher

```
$ pip install git+https://github.com/PenguinBoi12/dachshund.git
```

#### 2- Build a page and start the dashboard
```python
import dachshund
from dachshund import Number, Page, TimeSeriesChart

page = Page("overview", title="Overview")
latency = page.add(TimeSeriesChart("latency"))
users = page.add(Number("users"))
page.row(latency, users, widths=(2, 1))

dachshund.include(page)
dachshund.init("My service")
```

#### 3- Emit events
```python
dachshund.emit("latency", value=96)
dachshund.emit("users", value=1204)
```

Open http://127.0.0.1:1212 and the cards fill in as events arrive.

## Development
```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

Run the checks:

```bash
black dachshund/ tests/
mypy dachshund
pytest
```

## License
Dachshund is released under MIT.
