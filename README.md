# Dachshund

An embedded, real-time hostable admin dashboard for any Python service: FastAPI, Flask,
Django, bots, workers, daemons, etc.

Dachshund runs as a thread inside your process, so there's no router to hook into and
no database to set up. Declare widgets in your code, emit events from anywhere, and
the dashboard updates live over WebSocket.

> **Under development.** Dachshund is not usable yet.

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

MIT
